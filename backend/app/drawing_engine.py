from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from .repositories import (
    add_object,
    clear_redo_stack,
    delete_all_objects,
    delete_object,
    find_latest_object,
    find_objects,
    get_artwork,
    get_last_operation,
    list_operation_group,
    mark_operation_status,
    new_id,
    record_operation,
    save_version,
    update_artwork,
    update_object,
)
from .schemas import ArtworkResponse, OperationRequest


SUPPORTED_OPERATION_TYPES = {
    "create_canvas",
    "add_object",
    "set_style",
    "set_style_many",
    "set_metadata",
    "set_metadata_many",
    "move_object",
    "move_many",
    "scale_object",
    "scale_many",
    "replace_shape",
    "replace_shape_many",
    "delete_object",
    "clear_canvas",
    "save_artwork",
    "export_artwork",
}
SUPPORTED_OBJECT_TYPES = {"rect", "circle", "ellipse", "triangle", "line", "arrow", "star", "text", "polygon", "path", "bezier", "image"}
REPLACEABLE_SHAPE_TYPES = {"rect", "circle", "ellipse", "triangle", "star"}
SUPPORTED_LAYER_IDS = {"background", "base", "middle", "foreground"}
MIN_SCALE_FACTOR = 0.05
MAX_SCALE_FACTOR = 20.0
MAX_MOVE_DELTA = 10000


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _validate_layer_id(layer_id: Any) -> str:
    if not isinstance(layer_id, str) or layer_id not in SUPPORTED_LAYER_IDS:
        raise ValueError(f"Unsupported layer_id: {layer_id}")
    return layer_id


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return [str(item) for item in value if str(item).strip()]


def _validated_drawing_object(obj: Any) -> dict[str, Any]:
    drawing_object = dict(_require_dict(obj, "object"))
    object_type = drawing_object.get("type")
    if not isinstance(object_type, str) or object_type not in SUPPORTED_OBJECT_TYPES:
        raise ValueError(f"Unsupported object type: {object_type}")
    drawing_object["geometry"] = dict(_require_dict(drawing_object.get("geometry", {}), "object.geometry"))
    drawing_object["style"] = dict(_require_dict(drawing_object.get("style", {}), "object.style"))
    if "layer_id" in drawing_object:
        drawing_object["layer_id"] = _validate_layer_id(drawing_object["layer_id"])
    if "semantic_tags" in drawing_object:
        drawing_object["semantic_tags"] = _normalize_string_list(drawing_object["semantic_tags"], "object.semantic_tags")
    if "transform" in drawing_object:
        drawing_object["transform"] = dict(_require_dict(drawing_object["transform"], "object.transform"))
    if "name" in drawing_object and drawing_object["name"] is not None:
        drawing_object["name"] = str(drawing_object["name"])[:80]
    return drawing_object


def _validated_style(value: Any) -> dict[str, Any]:
    return dict(_require_dict(value or {}, "style"))


def _validated_scale_factor(value: Any) -> float:
    try:
        factor = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid scale factor: {value}") from exc
    if not math.isfinite(factor) or factor < MIN_SCALE_FACTOR or factor > MAX_SCALE_FACTOR:
        raise ValueError(f"Scale factor must be between {MIN_SCALE_FACTOR} and {MAX_SCALE_FACTOR}")
    return factor


def _validated_delta(value: Any, field_name: str) -> int:
    try:
        delta = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc
    if abs(delta) > MAX_MOVE_DELTA:
        raise ValueError(f"{field_name} is too large")
    return delta


def _validated_replacement_shape(value: Any) -> str:
    shape = str(value or "").strip()
    if shape not in REPLACEABLE_SHAPE_TYPES:
        raise ValueError(f"Unsupported replacement shape: {shape}")
    return shape


def _validated_canvas_payload(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for key in ("width", "height"):
        if key not in payload or payload[key] is None:
            continue
        value = int(payload[key])
        if value < 64 or value > 4096:
            raise ValueError(f"{key} must be between 64 and 4096")
        updates[key] = value
    if payload.get("background") is not None:
        background = str(payload["background"])
        if not background or len(background) > 64:
            raise ValueError("background must be 1 to 64 characters")
        updates["background"] = background
    return updates


def _target_object_id(connection: sqlite3.Connection, artwork_id: str, target: dict[str, Any] | None) -> str:
    if target and target.get("object_id"):
        return str(target["object_id"])
    object_type = target.get("type") if target else None
    return find_latest_object(connection, artwork_id, object_type).id


def _target_object(connection: sqlite3.Connection, artwork_id: str, target: dict[str, Any] | None):
    object_id = _target_object_id(connection, artwork_id, target)
    return next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)


def _move_geometry(geometry: dict[str, Any], dx: int, dy: int) -> dict[str, Any]:
    moved = dict(geometry)
    for key in ("x", "cx", "x1", "x2"):
        if key in moved:
            moved[key] = moved[key] + dx
    for key in ("y", "cy", "y1", "y2"):
        if key in moved:
            moved[key] = moved[key] + dy
    if isinstance(moved.get("points"), list):
        moved["points"] = [_move_coordinate_dict(point, dx, dy) for point in moved["points"]]
    if isinstance(moved.get("commands"), list):
        moved["commands"] = [_move_coordinate_dict(command, dx, dy) for command in moved["commands"]]
    return moved


def _move_coordinate_dict(item: Any, dx: float, dy: float) -> Any:
    if not isinstance(item, dict):
        return item
    moved = dict(item)
    for key in ("x", "x1", "x2"):
        if key in moved:
            moved[key] = round(float(moved[key]) + dx, 2)
    for key in ("y", "y1", "y2"):
        if key in moved:
            moved[key] = round(float(moved[key]) + dy, 2)
    return moved


def _collect_coordinates(items: list[Any]) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("x", "x1", "x2"):
            if key in item:
                xs.append(float(item[key]))
        for key in ("y", "y1", "y2"):
            if key in item:
                ys.append(float(item[key]))
    return xs, ys


def _scale_coordinate_dict(item: Any, factor: float, center_x: float, center_y: float) -> Any:
    if not isinstance(item, dict):
        return item
    scaled = dict(item)
    for key in ("x", "x1", "x2"):
        if key in scaled:
            scaled[key] = round(center_x + (float(scaled[key]) - center_x) * factor, 2)
    for key in ("y", "y1", "y2"):
        if key in scaled:
            scaled[key] = round(center_y + (float(scaled[key]) - center_y) * factor, 2)
    return scaled


def _scale_geometry(geometry: dict[str, Any], factor: float) -> dict[str, Any]:
    scaled = dict(geometry)
    original_width = float(geometry["width"]) if "width" in geometry else None
    original_height = float(geometry["height"]) if "height" in geometry else None
    for key in ("radius", "rx", "ry", "size", "outerRadius", "innerRadius", "width", "height", "fontSize"):
        if key in scaled:
            scaled[key] = round(float(scaled[key]) * factor, 2)
    if original_width is not None and "x" in scaled:
        scaled["x"] = round(float(scaled["x"]) - ((float(scaled["width"]) - original_width) / 2), 2)
    if original_height is not None and "y" in scaled:
        scaled["y"] = round(float(scaled["y"]) - ((float(scaled["height"]) - original_height) / 2), 2)
    if isinstance(scaled.get("points"), list):
        xs, ys = _collect_coordinates(scaled["points"])
        if xs and ys:
            center_x = (min(xs) + max(xs)) / 2
            center_y = (min(ys) + max(ys)) / 2
            scaled["points"] = [_scale_coordinate_dict(point, factor, center_x, center_y) for point in scaled["points"]]
    if isinstance(scaled.get("commands"), list):
        xs, ys = _collect_coordinates(scaled["commands"])
        if xs and ys:
            center_x = (min(xs) + max(xs)) / 2
            center_y = (min(ys) + max(ys)) / 2
            scaled["commands"] = [_scale_coordinate_dict(command, factor, center_x, center_y) for command in scaled["commands"]]
    return scaled


def _bounds_for_object(object_type: str, geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    if object_type == "rect" or "width" in geometry or "height" in geometry:
        x = float(geometry.get("x", 0))
        y = float(geometry.get("y", 0))
        return x, y, x + float(geometry.get("width", 100)), y + float(geometry.get("height", 100))
    if object_type == "circle":
        radius = float(geometry.get("radius", 50))
        cx = float(geometry.get("cx", 0))
        cy = float(geometry.get("cy", 0))
        return cx - radius, cy - radius, cx + radius, cy + radius
    if object_type == "ellipse":
        rx = float(geometry.get("rx", 60))
        ry = float(geometry.get("ry", 40))
        cx = float(geometry.get("cx", 0))
        cy = float(geometry.get("cy", 0))
        return cx - rx, cy - ry, cx + rx, cy + ry
    if object_type == "triangle":
        size = float(geometry.get("size", 100))
        x = float(geometry.get("x", 0))
        y = float(geometry.get("y", 0))
        height = size * 0.86
        return x - size / 2, y - height / 2, x + size / 2, y + height / 2
    if object_type == "star":
        radius = float(geometry.get("outerRadius", 50))
        cx = float(geometry.get("cx", 0))
        cy = float(geometry.get("cy", 0))
        return cx - radius, cy - radius, cx + radius, cy + radius
    coordinates: list[dict[str, Any]] = []
    if isinstance(geometry.get("points"), list):
        coordinates.extend(item for item in geometry["points"] if isinstance(item, dict))
    if isinstance(geometry.get("commands"), list):
        coordinates.extend(item for item in geometry["commands"] if isinstance(item, dict))
    xs, ys = _collect_coordinates(coordinates)
    if xs and ys:
        return min(xs), min(ys), max(xs), max(ys)
    return 462, 334, 562, 434


def _geometry_for_shape(shape: str, bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    left, top, right, bottom = bounds
    width = max(1, right - left)
    height = max(1, bottom - top)
    cx = left + width / 2
    cy = top + height / 2
    if shape == "circle":
        return {"cx": round(cx, 2), "cy": round(cy, 2), "radius": round(min(width, height) / 2, 2)}
    if shape == "ellipse":
        return {"cx": round(cx, 2), "cy": round(cy, 2), "rx": round(width / 2, 2), "ry": round(height / 2, 2)}
    if shape == "triangle":
        return {"x": round(cx, 2), "y": round(cy, 2), "size": round(min(width, height) * 1.1, 2)}
    if shape == "star":
        outer_radius = round(min(width, height) / 2, 2)
        return {"cx": round(cx, 2), "cy": round(cy, 2), "outerRadius": outer_radius, "innerRadius": round(outer_radius * 0.45, 2), "points": 5}
    return {"x": round(left, 2), "y": round(top, 2), "width": round(width, 2), "height": round(height, 2), "radius": 8}


def _replace_object_shape(
    connection: sqlite3.Connection,
    artwork_id: str,
    object_id: str,
    new_type: str,
    *,
    commit: bool,
) -> None:
    current = _target_object(connection, artwork_id, {"object_id": object_id})
    geometry = _geometry_for_shape(new_type, _bounds_for_object(current.type, current.geometry))
    update_object(connection, artwork_id, object_id, object_type=new_type, geometry=geometry, replace_geometry=True, commit=commit)


def _metadata_snapshot(obj) -> dict[str, Any]:
    return {
        "name": obj.name,
        "layer_id": obj.layer_id,
        "group_id": obj.group_id,
        "semantic_tags": obj.semantic_tags,
        "transform": obj.transform,
    }


def _metadata_updates(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = None if payload["name"] is None else str(payload["name"])[:80]
    if "layer_id" in payload:
        updates["layer_id"] = _validate_layer_id(payload["layer_id"])
    if "group_id" in payload:
        updates["group_id"] = None if payload["group_id"] is None else str(payload["group_id"])[:80]
    if "semantic_tags" in payload:
        updates["semantic_tags"] = _normalize_string_list(payload["semantic_tags"], "semantic_tags")
    if "transform" in payload:
        updates["transform"] = dict(_require_dict(payload["transform"], "transform"))
    return updates


def _apply_metadata_updates(connection: sqlite3.Connection, artwork_id: str, object_id: str, updates: dict[str, Any], *, commit: bool) -> None:
    kwargs = {key: value for key, value in updates.items() if key in {"name", "layer_id", "group_id", "semantic_tags", "transform"}}
    update_object(connection, artwork_id, object_id, **kwargs, commit=commit)


def apply_operation(
    connection: sqlite3.Connection,
    artwork_id: str,
    operation: OperationRequest,
    *,
    record: bool = True,
    clear_redo: bool = True,
    command_group_id: str | None = None,
    operation_index: int = 0,
    commit: bool = True,
) -> str:
    operation_type = operation.operation_type
    payload = dict(operation.payload)
    inverse_payload: dict[str, Any] = {}

    if operation_type not in SUPPORTED_OPERATION_TYPES:
        raise ValueError(f"Unsupported operation type: {operation_type}")

    should_clear_redo = clear_redo and record and operation_type not in {"undo", "redo"}

    if operation_type == "create_canvas":
        current = get_artwork(connection, artwork_id)
        inverse_payload = {"width": current.width, "height": current.height, "background": current.background}
        canvas_updates = _validated_canvas_payload(payload)
        update_artwork(
            connection,
            artwork_id,
            width=canvas_updates.get("width"),
            height=canvas_updates.get("height"),
            background=canvas_updates.get("background"),
            commit=commit,
        )
        message = "已更新画布"
    elif operation_type == "add_object":
        payload["object"] = _validated_drawing_object(payload.get("object"))
        created = add_object(connection, artwork_id, payload["object"], commit=commit)
        payload["object"] = created.model_dump()
        inverse_payload = {"object_id": created.id}
        message = f"已添加{created.name or created.type}"
    elif operation_type == "set_style":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = find_latest_object(connection, artwork_id) if payload.get("target", {}).get("selector") == "latest" else None
        if current is None:
            current = next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)
        style_updates = _validated_style(payload.get("style", {}))
        inverse_payload = {"target": {"object_id": object_id}, "style": {key: current.style.get(key) for key in style_updates}}
        update_object(connection, artwork_id, object_id, style=style_updates, commit=commit)
        message = "已更新样式"
    elif operation_type == "set_metadata":
        current = _target_object(connection, artwork_id, payload.get("target"))
        updates = _metadata_updates(payload)
        inverse_payload = {"target": {"object_id": current.id}, **{key: _metadata_snapshot(current)[key] for key in updates}}
        _apply_metadata_updates(connection, artwork_id, current.id, updates, commit=commit)
        message = "已更新对象信息"
    elif operation_type == "set_style_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        style_updates = _validated_style(payload.get("style", {}))
        inverse_payload = {
            "items": [
                {"object_id": obj.id, "style": {key: obj.style.get(key) for key in style_updates}}
                for obj in targets
            ]
        }
        payload["target"] = {"object_ids": [obj.id for obj in targets]}
        for obj in targets:
            update_object(connection, artwork_id, obj.id, style=style_updates, commit=commit)
        message = f"已更新 {len(targets)} 个对象的样式"
    elif operation_type == "set_metadata_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        updates = _metadata_updates(payload)
        inverse_payload = {
            "items": [
                {"object_id": obj.id, **{key: _metadata_snapshot(obj)[key] for key in updates}}
                for obj in targets
            ]
        }
        payload["target"] = {"object_ids": [obj.id for obj in targets]}
        for obj in targets:
            _apply_metadata_updates(connection, artwork_id, obj.id, updates, commit=commit)
        message = f"已更新 {len(targets)} 个对象信息"
    elif operation_type == "move_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = find_latest_object(connection, artwork_id) if payload.get("target", {}).get("selector") == "latest" else None
        if current is None:
            current = next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)
        dx = _validated_delta(payload.get("dx", 0), "dx")
        dy = _validated_delta(payload.get("dy", 0), "dy")
        update_object(connection, artwork_id, object_id, geometry=_move_geometry(current.geometry, dx, dy), commit=commit)
        inverse_payload = {"target": {"object_id": object_id}, "dx": -dx, "dy": -dy}
        message = "已移动对象"
    elif operation_type == "move_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        dx = _validated_delta(payload.get("dx", 0), "dx")
        dy = _validated_delta(payload.get("dy", 0), "dy")
        payload["target"] = {"object_ids": [obj.id for obj in targets]}
        inverse_payload = {"target": {"object_ids": [obj.id for obj in targets]}, "dx": -dx, "dy": -dy}
        for obj in targets:
            update_object(connection, artwork_id, obj.id, geometry=_move_geometry(obj.geometry, dx, dy), commit=commit)
        message = f"已移动 {len(targets)} 个对象"
    elif operation_type == "scale_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = find_latest_object(connection, artwork_id) if payload.get("target", {}).get("selector") == "latest" else None
        if current is None:
            current = next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)
        factor = _validated_scale_factor(payload.get("factor", 1))
        update_object(connection, artwork_id, object_id, geometry=_scale_geometry(current.geometry, factor), commit=commit)
        inverse_payload = {"target": {"object_id": object_id}, "factor": 1 / factor}
        message = "已缩放对象"
    elif operation_type == "scale_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        factor = _validated_scale_factor(payload.get("factor", 1))
        payload["target"] = {"object_ids": [obj.id for obj in targets]}
        inverse_payload = {"target": {"object_ids": [obj.id for obj in targets]}, "factor": 1 / factor}
        for obj in targets:
            update_object(connection, artwork_id, obj.id, geometry=_scale_geometry(obj.geometry, factor), commit=commit)
        message = f"已缩放 {len(targets)} 个对象"
    elif operation_type == "replace_shape":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = _target_object(connection, artwork_id, {"object_id": object_id})
        new_type = _validated_replacement_shape(payload.get("shape") or payload.get("type"))
        inverse_payload = {"target": {"object_id": object_id}, "shape": current.type, "geometry": current.geometry}
        payload["target"] = {"object_id": object_id}
        payload["shape"] = new_type
        _replace_object_shape(connection, artwork_id, object_id, new_type, commit=commit)
        message = "已替换对象形状"
    elif operation_type == "replace_shape_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        new_type = _validated_replacement_shape(payload.get("shape") or payload.get("type"))
        payload["target"] = {"object_ids": [obj.id for obj in targets]}
        payload["shape"] = new_type
        inverse_payload = {
            "items": [{"object_id": obj.id, "shape": obj.type, "geometry": obj.geometry} for obj in targets]
        }
        for obj in targets:
            _replace_object_shape(connection, artwork_id, obj.id, new_type, commit=commit)
        message = f"已替换 {len(targets)} 个对象形状"
    elif operation_type == "delete_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        removed = delete_object(connection, artwork_id, object_id, commit=commit)
        inverse_payload = {"object": removed.model_dump()}
        message = "已删除对象"
    elif operation_type == "clear_canvas":
        removed_objects = delete_all_objects(connection, artwork_id, commit=commit)
        inverse_payload = {"objects": [obj.model_dump() for obj in removed_objects]}
        payload["object_count"] = len(removed_objects)
        message = "已清空画布" if removed_objects else "画布已经是空的"
    elif operation_type == "save_artwork":
        title = payload.get("title")
        if title:
            update_artwork(connection, artwork_id, title=title, commit=commit)
        save_version(connection, artwork_id, commit=commit)
        inverse_payload = {}
        message = "已保存作品版本"
    elif operation_type == "export_artwork":
        inverse_payload = {}
        message = "已准备导出"

    if record and operation_type not in {"export_artwork"}:
        if should_clear_redo:
            clear_redo_stack(connection, artwork_id, commit=commit)
        record_operation(
            connection,
            artwork_id,
            operation_type,
            payload,
            inverse_payload,
            command_group_id=command_group_id,
            operation_index=operation_index,
            commit=commit,
        )
    return message


def apply_operation_plan(connection: sqlite3.Connection, artwork_id: str, operations: list[OperationRequest]) -> str:
    messages: list[str] = []
    command_group_id = new_id() if operations else None
    try:
        clear_redo_stack(connection, artwork_id, commit=False)
        for operation_index, operation in enumerate(operations):
            messages.append(
                apply_operation(
                    connection,
                    artwork_id,
                    operation,
                    clear_redo=False,
                    command_group_id=command_group_id,
                    operation_index=operation_index,
                    commit=False,
                )
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return messages[-1] if messages else "未执行任何操作"


def _row_command_group_id(row: sqlite3.Row) -> str | None:
    if "command_group_id" not in row.keys():
        return None
    value = row["command_group_id"]
    return str(value) if value else None


def _operation_rows_for_history_step(
    connection: sqlite3.Connection,
    artwork_id: str,
    row: sqlite3.Row,
    status: str,
) -> list[sqlite3.Row]:
    command_group_id = _row_command_group_id(row)
    if not command_group_id:
        return [row]
    rows = list_operation_group(connection, artwork_id, command_group_id, status)
    return rows or [row]


def _undo_operation_row(connection: sqlite3.Connection, artwork_id: str, row: sqlite3.Row, *, commit: bool) -> None:
    operation_type = row["operation_type"]
    inverse_payload = json.loads(row["inverse_payload_json"])

    if operation_type == "create_canvas":
        update_artwork(connection, artwork_id, **inverse_payload, commit=commit)
    elif operation_type == "add_object":
        delete_object(connection, artwork_id, inverse_payload["object_id"], commit=commit)
    elif operation_type == "set_style":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="set_style", payload=inverse_payload), record=False, clear_redo=False, commit=commit)
    elif operation_type == "set_metadata":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="set_metadata", payload=inverse_payload), record=False, clear_redo=False, commit=commit)
    elif operation_type == "set_style_many":
        for item in inverse_payload["items"]:
            update_object(connection, artwork_id, item["object_id"], style=item["style"], commit=commit)
    elif operation_type == "set_metadata_many":
        for item in inverse_payload["items"]:
            update_object(
                connection,
                artwork_id,
                item["object_id"],
                name=item.get("name"),
                layer_id=item.get("layer_id"),
                group_id=item.get("group_id"),
                semantic_tags=item.get("semantic_tags", []),
                transform=item.get("transform", {}),
                commit=commit,
            )
    elif operation_type == "move_object":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="move_object", payload=inverse_payload), record=False, clear_redo=False, commit=commit)
    elif operation_type == "move_many":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="move_many", payload=inverse_payload), record=False, clear_redo=False, commit=commit)
    elif operation_type == "scale_object":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="scale_object", payload=inverse_payload), record=False, clear_redo=False, commit=commit)
    elif operation_type == "scale_many":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="scale_many", payload=inverse_payload), record=False, clear_redo=False, commit=commit)
    elif operation_type == "replace_shape":
        update_object(
            connection,
            artwork_id,
            inverse_payload["target"]["object_id"],
            object_type=inverse_payload["shape"],
            geometry=inverse_payload["geometry"],
            replace_geometry=True,
            commit=commit,
        )
    elif operation_type == "replace_shape_many":
        for item in inverse_payload["items"]:
            update_object(connection, artwork_id, item["object_id"], object_type=item["shape"], geometry=item["geometry"], replace_geometry=True, commit=commit)
    elif operation_type == "delete_object":
        add_object(connection, artwork_id, inverse_payload["object"], commit=commit)
    elif operation_type == "clear_canvas":
        for obj in inverse_payload.get("objects", []):
            add_object(connection, artwork_id, obj, commit=commit)


def _redo_operation_row(connection: sqlite3.Connection, artwork_id: str, row: sqlite3.Row, *, commit: bool) -> None:
    operation = OperationRequest(operation_type=row["operation_type"], payload=json.loads(row["payload_json"]))
    apply_operation(connection, artwork_id, operation, record=False, clear_redo=False, commit=commit)


def undo_last_operation(connection: sqlite3.Connection, artwork_id: str) -> ArtworkResponse:
    row = get_last_operation(connection, artwork_id, "applied")
    if row is None:
        return get_artwork(connection, artwork_id)

    rows = _operation_rows_for_history_step(connection, artwork_id, row, "applied")
    try:
        for operation_row in reversed(rows):
            _undo_operation_row(connection, artwork_id, operation_row, commit=False)
        for operation_row in rows:
            mark_operation_status(connection, operation_row["id"], "undone", commit=False)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return get_artwork(connection, artwork_id)


def redo_last_operation(connection: sqlite3.Connection, artwork_id: str) -> ArtworkResponse:
    row = get_last_operation(connection, artwork_id, "undone")
    if row is None:
        return get_artwork(connection, artwork_id)

    rows = _operation_rows_for_history_step(connection, artwork_id, row, "undone")
    try:
        for operation_row in rows:
            _redo_operation_row(connection, artwork_id, operation_row, commit=False)
        for operation_row in rows:
            mark_operation_status(connection, operation_row["id"], "applied", commit=False)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return get_artwork(connection, artwork_id)
