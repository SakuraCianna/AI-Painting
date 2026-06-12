from __future__ import annotations

import json
import sqlite3
from typing import Any

from .repositories import (
    add_object,
    clear_redo_stack,
    delete_object,
    find_latest_object,
    find_objects,
    get_artwork,
    get_last_operation,
    mark_operation_status,
    record_operation,
    save_version,
    update_artwork,
    update_object,
)
from .schemas import ArtworkResponse, OperationRequest


def _target_object_id(connection: sqlite3.Connection, artwork_id: str, target: dict[str, Any] | None) -> str:
    if target and target.get("object_id"):
        return str(target["object_id"])
    object_type = target.get("type") if target else None
    return find_latest_object(connection, artwork_id, object_type).id


def _move_geometry(geometry: dict[str, Any], dx: int, dy: int) -> dict[str, Any]:
    moved = dict(geometry)
    for key in ("x", "cx", "x1", "x2"):
        if key in moved:
            moved[key] = moved[key] + dx
    for key in ("y", "cy", "y1", "y2"):
        if key in moved:
            moved[key] = moved[key] + dy
    return moved


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
    return scaled


def apply_operation(
    connection: sqlite3.Connection,
    artwork_id: str,
    operation: OperationRequest,
    *,
    record: bool = True,
    clear_redo: bool = True,
    commit: bool = True,
) -> str:
    operation_type = operation.operation_type
    payload = dict(operation.payload)
    inverse_payload: dict[str, Any] = {}

    if clear_redo and record and operation_type not in {"undo", "redo"}:
        clear_redo_stack(connection, artwork_id, commit=commit)

    if operation_type == "create_canvas":
        current = get_artwork(connection, artwork_id)
        inverse_payload = {"width": current.width, "height": current.height, "background": current.background}
        update_artwork(
            connection,
            artwork_id,
            width=payload.get("width"),
            height=payload.get("height"),
            background=payload.get("background"),
            commit=commit,
        )
        message = "已更新画布"
    elif operation_type == "add_object":
        created = add_object(connection, artwork_id, payload["object"], commit=commit)
        payload["object"] = created.model_dump()
        inverse_payload = {"object_id": created.id}
        message = f"已添加{created.name or created.type}"
    elif operation_type == "set_style":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = find_latest_object(connection, artwork_id) if payload.get("target", {}).get("selector") == "latest" else None
        if current is None:
            current = next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)
        style_updates = payload.get("style", {})
        inverse_payload = {"target": {"object_id": object_id}, "style": {key: current.style.get(key) for key in style_updates}}
        update_object(connection, artwork_id, object_id, style=style_updates, commit=commit)
        message = "已更新样式"
    elif operation_type == "set_style_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        style_updates = payload.get("style", {})
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
    elif operation_type == "move_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = find_latest_object(connection, artwork_id) if payload.get("target", {}).get("selector") == "latest" else None
        if current is None:
            current = next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)
        dx = int(payload.get("dx", 0))
        dy = int(payload.get("dy", 0))
        update_object(connection, artwork_id, object_id, geometry=_move_geometry(current.geometry, dx, dy), commit=commit)
        inverse_payload = {"target": {"object_id": object_id}, "dx": -dx, "dy": -dy}
        message = "已移动对象"
    elif operation_type == "move_many":
        targets = find_objects(connection, artwork_id, payload.get("target"))
        if not targets:
            raise KeyError("No matching drawing objects exist")
        dx = int(payload.get("dx", 0))
        dy = int(payload.get("dy", 0))
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
        factor = float(payload.get("factor", 1))
        update_object(connection, artwork_id, object_id, geometry=_scale_geometry(current.geometry, factor), commit=commit)
        inverse_payload = {"target": {"object_id": object_id}, "factor": 1 / factor if factor else 1}
        message = "已缩放对象"
    elif operation_type == "delete_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        removed = delete_object(connection, artwork_id, object_id, commit=commit)
        inverse_payload = {"object": removed.model_dump()}
        message = "已删除对象"
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
    else:
        raise ValueError(f"Unsupported operation type: {operation_type}")

    if record and operation_type not in {"export_artwork"}:
        record_operation(connection, artwork_id, operation_type, payload, inverse_payload, commit=commit)
    return message


def apply_operation_plan(connection: sqlite3.Connection, artwork_id: str, operations: list[OperationRequest]) -> str:
    messages: list[str] = []
    try:
        clear_redo_stack(connection, artwork_id, commit=False)
        for operation in operations:
            messages.append(apply_operation(connection, artwork_id, operation, clear_redo=False, commit=False))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return messages[-1] if messages else "未执行任何操作"


def undo_last_operation(connection: sqlite3.Connection, artwork_id: str) -> ArtworkResponse:
    row = get_last_operation(connection, artwork_id, "applied")
    if row is None:
        return get_artwork(connection, artwork_id)

    operation_type = row["operation_type"]
    inverse_payload = json.loads(row["inverse_payload_json"])

    if operation_type == "create_canvas":
        update_artwork(connection, artwork_id, **inverse_payload)
    elif operation_type == "add_object":
        delete_object(connection, artwork_id, inverse_payload["object_id"])
    elif operation_type == "set_style":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="set_style", payload=inverse_payload), record=False)
    elif operation_type == "set_style_many":
        for item in inverse_payload["items"]:
            update_object(connection, artwork_id, item["object_id"], style=item["style"])
    elif operation_type == "move_object":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="move_object", payload=inverse_payload), record=False)
    elif operation_type == "move_many":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="move_many", payload=inverse_payload), record=False)
    elif operation_type == "scale_object":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="scale_object", payload=inverse_payload), record=False)
    elif operation_type == "delete_object":
        add_object(connection, artwork_id, inverse_payload["object"])

    mark_operation_status(connection, row["id"], "undone")
    return get_artwork(connection, artwork_id)


def redo_last_operation(connection: sqlite3.Connection, artwork_id: str) -> ArtworkResponse:
    row = get_last_operation(connection, artwork_id, "undone")
    if row is None:
        return get_artwork(connection, artwork_id)

    operation = OperationRequest(operation_type=row["operation_type"], payload=json.loads(row["payload_json"]))
    apply_operation(connection, artwork_id, operation, record=False, clear_redo=False)
    mark_operation_status(connection, row["id"], "applied")
    return get_artwork(connection, artwork_id)
