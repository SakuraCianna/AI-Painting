from __future__ import annotations

import json
import sqlite3
from typing import Any

from .repositories import (
    add_object,
    clear_redo_stack,
    delete_object,
    find_latest_object,
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


def apply_operation(
    connection: sqlite3.Connection,
    artwork_id: str,
    operation: OperationRequest,
    *,
    record: bool = True,
    clear_redo: bool = True,
) -> str:
    operation_type = operation.operation_type
    payload = dict(operation.payload)
    inverse_payload: dict[str, Any] = {}

    if clear_redo and record and operation_type not in {"undo", "redo"}:
        clear_redo_stack(connection, artwork_id)

    if operation_type == "create_canvas":
        current = get_artwork(connection, artwork_id)
        inverse_payload = {"width": current.width, "height": current.height, "background": current.background}
        update_artwork(
            connection,
            artwork_id,
            width=payload.get("width"),
            height=payload.get("height"),
            background=payload.get("background"),
        )
        message = "已更新画布"
    elif operation_type == "add_object":
        created = add_object(connection, artwork_id, payload["object"])
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
        update_object(connection, artwork_id, object_id, style=style_updates)
        message = "已更新样式"
    elif operation_type == "move_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        current = find_latest_object(connection, artwork_id) if payload.get("target", {}).get("selector") == "latest" else None
        if current is None:
            current = next(obj for obj in get_artwork(connection, artwork_id).objects if obj.id == object_id)
        dx = int(payload.get("dx", 0))
        dy = int(payload.get("dy", 0))
        update_object(connection, artwork_id, object_id, geometry=_move_geometry(current.geometry, dx, dy))
        inverse_payload = {"target": {"object_id": object_id}, "dx": -dx, "dy": -dy}
        message = "已移动对象"
    elif operation_type == "delete_object":
        object_id = _target_object_id(connection, artwork_id, payload.get("target"))
        removed = delete_object(connection, artwork_id, object_id)
        inverse_payload = {"object": removed.model_dump()}
        message = "已删除对象"
    elif operation_type == "save_artwork":
        title = payload.get("title")
        if title:
            update_artwork(connection, artwork_id, title=title)
        save_version(connection, artwork_id)
        inverse_payload = {}
        message = "已保存作品版本"
    elif operation_type == "export_artwork":
        inverse_payload = {}
        message = "已准备导出"
    else:
        raise ValueError(f"Unsupported operation type: {operation_type}")

    if record and operation_type not in {"export_artwork"}:
        record_operation(connection, artwork_id, operation_type, payload, inverse_payload)
    return message


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
    elif operation_type == "move_object":
        apply_operation(connection, artwork_id, OperationRequest(operation_type="move_object", payload=inverse_payload), record=False)
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
