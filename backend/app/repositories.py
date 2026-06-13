from __future__ import annotations

import colorsys
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .schemas import ArtworkCreateRequest, ArtworkResponse, DrawingObject


_UNSET = object()
POSITION_ALIASES = {
    "left": "leftmost",
    "right": "rightmost",
    "top": "topmost",
    "bottom": "bottommost",
}
POSITION_SORT_CONFIG = {
    "leftmost": (0, False),
    "rightmost": (0, True),
    "topmost": (1, False),
    "bottommost": (1, True),
}
RELATION_ALIASES = {
    "below": "below",
    "under": "below",
    "above": "above",
    "over": "above",
    "left_of": "left_of",
    "right_of": "right_of",
    "near": "near",
}
WARM_COLOR_HEXES = {"#dc2626", "#ef4444", "#f97316", "#fb923c", "#facc15", "#fde047", "#92400e", "#a16207", "#7c2d12"}
COOL_COLOR_HEXES = {"#2563eb", "#1d4ed8", "#7dd3fc", "#93c5fd", "#16a34a", "#22c55e", "#15803d", "#1e3a8a"}
NEUTRAL_COLOR_HEXES = {"#ffffff", "#faf7ed", "#f8fafc", "#f3f4f6", "#e5e7eb", "#d1d5db", "#6b7280", "#374151", "#111827"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def _json(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _loads(raw: str) -> Any:
    return json.loads(raw)


def _commit(connection: sqlite3.Connection, commit: bool) -> None:
    if commit:
        connection.commit()


def row_to_object(row: sqlite3.Row) -> DrawingObject:
    return DrawingObject(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        geometry=_loads(row["geometry_json"]),
        style=_loads(row["style_json"]),
        z_index=row["z_index"],
        layer_id=row["layer_id"] or "base",
        group_id=row["group_id"],
        semantic_tags=_loads(row["semantic_tags_json"]),
        transform=_loads(row["transform_json"]),
    )


def create_artwork(connection: sqlite3.Connection, request: ArtworkCreateRequest, *, commit: bool = True) -> ArtworkResponse:
    artwork_id = new_id()
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO artworks (id, title, width, height, background, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (artwork_id, request.title, request.width, request.height, request.background, timestamp, timestamp),
    )
    _commit(connection, commit)
    return get_artwork(connection, artwork_id)


def list_artworks(connection: sqlite3.Connection) -> list[ArtworkResponse]:
    rows = connection.execute("SELECT id FROM artworks ORDER BY updated_at DESC").fetchall()
    return [get_artwork(connection, row["id"]) for row in rows]


def get_artwork(connection: sqlite3.Connection, artwork_id: str) -> ArtworkResponse:
    artwork = connection.execute("SELECT * FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
    if artwork is None:
        raise KeyError(f"Artwork {artwork_id} does not exist")

    objects = connection.execute(
        "SELECT * FROM drawing_objects WHERE artwork_id = ? ORDER BY z_index ASC, created_at ASC",
        (artwork_id,),
    ).fetchall()
    return ArtworkResponse(
        id=artwork["id"],
        title=artwork["title"],
        width=artwork["width"],
        height=artwork["height"],
        background=artwork["background"],
        objects=[row_to_object(row) for row in objects],
        created_at=artwork["created_at"],
        updated_at=artwork["updated_at"],
    )


def update_artwork(
    connection: sqlite3.Connection,
    artwork_id: str,
    *,
    title: str | None = None,
    width: int | None = None,
    height: int | None = None,
    background: str | None = None,
    commit: bool = True,
) -> ArtworkResponse:
    current = get_artwork(connection, artwork_id)
    connection.execute(
        """
        UPDATE artworks
        SET title = ?, width = ?, height = ?, background = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            title if title is not None else current.title,
            width if width is not None else current.width,
            height if height is not None else current.height,
            background if background is not None else current.background,
            now_iso(),
            artwork_id,
        ),
    )
    _commit(connection, commit)
    return get_artwork(connection, artwork_id)


def get_next_z_index(connection: sqlite3.Connection, artwork_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(z_index), -1) + 1 AS next_z FROM drawing_objects WHERE artwork_id = ?",
        (artwork_id,),
    ).fetchone()
    return int(row["next_z"])


def add_object(connection: sqlite3.Connection, artwork_id: str, obj: dict[str, Any], *, commit: bool = True) -> DrawingObject:
    timestamp = now_iso()
    object_id = obj.get("id") or new_id()
    z_index = int(obj.get("z_index", get_next_z_index(connection, artwork_id)))
    connection.execute(
        """
        INSERT INTO drawing_objects
            (id, artwork_id, type, name, layer_id, group_id, semantic_tags_json, transform_json, geometry_json, style_json, z_index, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            object_id,
            artwork_id,
            obj["type"],
            obj.get("name"),
            obj.get("layer_id", "base"),
            obj.get("group_id"),
            _json(obj.get("semantic_tags", [])),
            _json(obj.get("transform", {})),
            _json(obj.get("geometry", {})),
            _json(obj.get("style", {})),
            z_index,
            timestamp,
            timestamp,
        ),
    )
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    _commit(connection, commit)
    return get_object(connection, artwork_id, object_id)


def get_object(connection: sqlite3.Connection, artwork_id: str, object_id: str) -> DrawingObject:
    row = connection.execute(
        "SELECT * FROM drawing_objects WHERE artwork_id = ? AND id = ?",
        (artwork_id, object_id),
    ).fetchone()
    if row is None:
        raise KeyError(f"Drawing object {object_id} does not exist")
    return row_to_object(row)


def find_latest_object(connection: sqlite3.Connection, artwork_id: str, object_type: str | None = None) -> DrawingObject:
    if object_type:
        row = connection.execute(
            """
            SELECT * FROM drawing_objects
            WHERE artwork_id = ? AND type = ?
            ORDER BY z_index DESC, created_at DESC
            LIMIT 1
            """,
            (artwork_id, object_type),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT * FROM drawing_objects
            WHERE artwork_id = ?
            ORDER BY z_index DESC, created_at DESC
            LIMIT 1
            """,
            (artwork_id,),
        ).fetchone()
    if row is None:
        raise KeyError("No matching drawing object exists")
    return row_to_object(row)


def find_objects(connection: sqlite3.Connection, artwork_id: str, selector: dict[str, Any] | None) -> list[DrawingObject]:
    selector = selector or {"selector": "all"}
    if selector.get("object_ids"):
        object_ids = [str(object_id) for object_id in selector["object_ids"]]
        placeholders = ",".join("?" for _ in object_ids)
        rows = connection.execute(
            f"""
            SELECT * FROM drawing_objects
            WHERE artwork_id = ? AND id IN ({placeholders})
            ORDER BY z_index ASC, created_at ASC
            """,
            (artwork_id, *object_ids),
        ).fetchall()
        return [row_to_object(row) for row in rows]

    if selector.get("selector") == "latest":
        return [find_latest_object(connection, artwork_id, selector.get("type"))]

    object_type = selector.get("type")
    if object_type:
        rows = connection.execute(
            """
            SELECT * FROM drawing_objects
            WHERE artwork_id = ? AND type = ?
            ORDER BY z_index ASC, created_at ASC
            """,
            (artwork_id, object_type),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM drawing_objects
            WHERE artwork_id = ?
            ORDER BY z_index ASC, created_at ASC
            """,
            (artwork_id,),
        ).fetchall()

    objects = [row_to_object(row) for row in rows]
    color = selector.get("color")
    if color:
        objects = [obj for obj in objects if obj.style.get("fill") == color or obj.style.get("stroke") == color]
    color_group = selector.get("color_group")
    if color_group:
        objects = [obj for obj in objects if _object_matches_color_group(obj, str(color_group))]
    name = selector.get("name")
    if name:
        objects = [obj for obj in objects if obj.name == name]
    name_contains = selector.get("name_contains")
    if name_contains:
        objects = [obj for obj in objects if obj.name and str(name_contains) in obj.name]
    layer_id = selector.get("layer_id")
    if layer_id:
        objects = [obj for obj in objects if obj.layer_id == layer_id]
    group_id = selector.get("group_id")
    if group_id:
        objects = [obj for obj in objects if obj.group_id == group_id]
    semantic_tag = selector.get("semantic_tag")
    if semantic_tag:
        objects = [obj for obj in objects if semantic_tag in obj.semantic_tags]
    semantic_tags = selector.get("semantic_tags")
    if semantic_tags:
        wanted_tags = {str(tag) for tag in semantic_tags}
        objects = [obj for obj in objects if wanted_tags.intersection(obj.semantic_tags)]
    size_class = selector.get("size_class") or selector.get("size")
    if size_class:
        objects = _filter_objects_by_size(objects, str(size_class), selector.get("max_area"))
    elif selector.get("max_area") is not None:
        objects = _filter_objects_by_size(objects, "max_area", selector.get("max_area"))
    relative_to = selector.get("relative_to")
    if relative_to and objects:
        objects = _filter_objects_by_relation(connection, artwork_id, objects, relative_to)
    position = selector.get("position")
    if position and objects:
        objects = _filter_objects_by_position(objects, str(position), selector)
    return objects


def _object_bounds(obj: DrawingObject) -> tuple[float, float, float, float]:
    geometry = obj.geometry
    object_type = obj.type
    if object_type == "rect" or "width" in geometry or "height" in geometry:
        x = float(geometry.get("x", 0))
        y = float(geometry.get("y", 0))
        width = float(geometry.get("width", geometry.get("size", 0)))
        height = float(geometry.get("height", geometry.get("size", 0)))
        return x, y, x + width, y + height
    if object_type == "circle":
        radius = float(geometry.get("radius", 0))
        cx = float(geometry.get("cx", 0))
        cy = float(geometry.get("cy", 0))
        return cx - radius, cy - radius, cx + radius, cy + radius
    if object_type == "ellipse":
        rx = float(geometry.get("rx", 0))
        ry = float(geometry.get("ry", 0))
        cx = float(geometry.get("cx", 0))
        cy = float(geometry.get("cy", 0))
        return cx - rx, cy - ry, cx + rx, cy + ry
    if object_type == "triangle":
        size = float(geometry.get("size", 0))
        x = float(geometry.get("x", 0))
        y = float(geometry.get("y", 0))
        height = size * 0.86
        return x - size / 2, y - height / 2, x + size / 2, y + height / 2
    if object_type == "star":
        radius = float(geometry.get("outerRadius", geometry.get("radius", 0)))
        cx = float(geometry.get("cx", 0))
        cy = float(geometry.get("cy", 0))
        return cx - radius, cy - radius, cx + radius, cy + radius

    coordinates: list[dict[str, Any]] = []
    if isinstance(geometry.get("points"), list):
        coordinates.extend(point for point in geometry["points"] if isinstance(point, dict))
    if isinstance(geometry.get("commands"), list):
        coordinates.extend(command for command in geometry["commands"] if isinstance(command, dict))
    xs = [float(item[key]) for item in coordinates for key in ("x", "x1", "x2") if key in item]
    ys = [float(item[key]) for item in coordinates for key in ("y", "y1", "y2") if key in item]
    if xs and ys:
        return min(xs), min(ys), max(xs), max(ys)
    center_x, center_y = _object_center(obj)
    return center_x, center_y, center_x, center_y


def _object_center(obj: DrawingObject) -> tuple[float, float]:
    geometry = obj.geometry
    if "cx" in geometry or "cy" in geometry:
        return float(geometry.get("cx", 0)), float(geometry.get("cy", 0))
    if "x" in geometry or "y" in geometry:
        width = float(geometry.get("width", geometry.get("size", 0)))
        height = float(geometry.get("height", geometry.get("size", 0)))
        return float(geometry.get("x", 0)) + width / 2, float(geometry.get("y", 0)) + height / 2
    points = geometry.get("points")
    if isinstance(points, list) and points:
        xs = [float(point.get("x", 0)) for point in points if isinstance(point, dict)]
        ys = [float(point.get("y", 0)) for point in points if isinstance(point, dict)]
        if xs and ys:
            return sum(xs) / len(xs), sum(ys) / len(ys)
    commands = geometry.get("commands")
    if isinstance(commands, list) and commands:
        xs = [float(command.get("x", 0)) for command in commands if isinstance(command, dict) and "x" in command]
        ys = [float(command.get("y", 0)) for command in commands if isinstance(command, dict) and "y" in command]
        if xs and ys:
            return sum(xs) / len(xs), sum(ys) / len(ys)
    return 0, 0


def _style_colors(obj: DrawingObject) -> list[str]:
    return [str(color) for color in (obj.style.get("fill"), obj.style.get("stroke")) if color]


def _normalize_hex_color(color: str) -> str | None:
    normalized = color.strip().lower()
    if normalized == "transparent" or not normalized.startswith("#"):
        return None
    if len(normalized) == 4:
        return "#" + "".join(channel * 2 for channel in normalized[1:])
    if len(normalized) == 7:
        return normalized
    return None


def _color_temperature(color: str) -> str | None:
    normalized = _normalize_hex_color(color)
    if normalized is None:
        return None
    if normalized in WARM_COLOR_HEXES:
        return "warm"
    if normalized in COOL_COLOR_HEXES:
        return "cool"
    if normalized in NEUTRAL_COLOR_HEXES:
        return "neutral"

    try:
        red = int(normalized[1:3], 16) / 255
        green = int(normalized[3:5], 16) / 255
        blue = int(normalized[5:7], 16) / 255
    except ValueError:
        return None
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    if saturation < 0.12 or value < 0.08:
        return "neutral"
    if hue <= 0.17 or hue >= 0.92:
        return "warm"
    if 0.17 < hue < 0.78:
        return "cool"
    return "warm"


def _object_matches_color_group(obj: DrawingObject, color_group: str) -> bool:
    normalized_group = color_group.strip().lower()
    if normalized_group in {"warm_color", "warm-colors", "暖色"}:
        normalized_group = "warm"
    elif normalized_group in {"cool_color", "cool-colors", "冷色"}:
        normalized_group = "cool"
    elif normalized_group in {"neutral_color", "neutral-colors", "中性色"}:
        normalized_group = "neutral"
    return any(_color_temperature(color) == normalized_group for color in _style_colors(obj))


def _object_area(obj: DrawingObject) -> float:
    left, top, right, bottom = _object_bounds(obj)
    return max(0.0, right - left) * max(0.0, bottom - top)


def _filter_objects_by_size(objects: list[DrawingObject], size_class: str, max_area: Any = None) -> list[DrawingObject]:
    try:
        area_limit = float(max_area) if max_area is not None else 25000.0
    except (TypeError, ValueError):
        area_limit = 25000.0
    normalized = size_class.strip().lower()
    if normalized in {"small", "小", "小物件", "max_area"}:
        return [obj for obj in objects if _object_area(obj) <= area_limit]
    if normalized in {"large", "大", "大物件"}:
        return [obj for obj in objects if _object_area(obj) > area_limit]
    return objects


def _relation_matches(candidate: DrawingObject, reference: DrawingObject, relation: str) -> bool:
    candidate_x, candidate_y = _object_center(candidate)
    reference_x, reference_y = _object_center(reference)
    if relation == "below":
        return candidate_y > reference_y
    if relation == "above":
        return candidate_y < reference_y
    if relation == "left_of":
        return candidate_x < reference_x
    if relation == "right_of":
        return candidate_x > reference_x
    if relation == "near":
        return abs(candidate_x - reference_x) <= 180 and abs(candidate_y - reference_y) <= 180
    return True


def _filter_objects_by_relation(
    connection: sqlite3.Connection,
    artwork_id: str,
    objects: list[DrawingObject],
    relation_selector: Any,
) -> list[DrawingObject]:
    if not isinstance(relation_selector, dict):
        return objects
    relation = RELATION_ALIASES.get(str(relation_selector.get("relation", "")).strip().lower())
    reference_selector = relation_selector.get("target") or relation_selector.get("selector")
    if not relation or not isinstance(reference_selector, dict):
        return objects
    references = find_objects(connection, artwork_id, reference_selector)
    if not references:
        return []
    return [
        obj
        for obj in objects
        if any(obj.id != reference.id and _relation_matches(obj, reference, relation) for reference in references)
    ]


def _selector_rank(selector: dict[str, Any]) -> int | None:
    raw_rank = selector.get("position_rank", selector.get("rank", selector.get("ordinal")))
    if raw_rank is None:
        return None
    try:
        rank = int(raw_rank)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def _filter_objects_by_position(objects: list[DrawingObject], position: str, selector: dict[str, Any]) -> list[DrawingObject]:
    normalized_position = POSITION_ALIASES.get(position, position)
    if normalized_position in POSITION_SORT_CONFIG:
        key_index, reverse = POSITION_SORT_CONFIG[normalized_position]
        sorted_objects = sorted(objects, key=lambda obj: _object_center(obj)[key_index], reverse=reverse)
        rank = _selector_rank(selector)
        if rank is not None:
            return [sorted_objects[rank - 1]] if rank <= len(sorted_objects) else []
        return [sorted_objects[0]]
    return objects


def update_object(
    connection: sqlite3.Connection,
    artwork_id: str,
    object_id: str,
    *,
    object_type: str | None = None,
    geometry: dict[str, Any] | None = None,
    replace_geometry: bool = False,
    style: dict[str, Any] | None = None,
    name: str | None | object = _UNSET,
    layer_id: str | None | object = _UNSET,
    group_id: str | None | object = _UNSET,
    semantic_tags: list[str] | None | object = _UNSET,
    transform: dict[str, Any] | object = _UNSET,
    commit: bool = True,
) -> DrawingObject:
    current = get_object(connection, artwork_id, object_id)
    next_geometry = dict(geometry or {}) if replace_geometry and geometry is not None else {**current.geometry, **(geometry or {})}
    next_style = {**current.style, **(style or {})}
    next_type = object_type or current.type
    next_name = current.name if name is _UNSET else name
    next_layer_id = current.layer_id if layer_id is _UNSET else layer_id or "base"
    next_group_id = current.group_id if group_id is _UNSET else group_id
    next_semantic_tags = current.semantic_tags if semantic_tags is _UNSET else semantic_tags or []
    next_transform = current.transform if transform is _UNSET else transform
    timestamp = now_iso()
    connection.execute(
        """
        UPDATE drawing_objects
        SET type = ?, name = ?, layer_id = ?, group_id = ?, semantic_tags_json = ?, transform_json = ?, geometry_json = ?, style_json = ?, updated_at = ?
        WHERE artwork_id = ? AND id = ?
        """,
        (
            next_type,
            next_name,
            next_layer_id,
            next_group_id,
            _json(next_semantic_tags),
            _json(next_transform),
            _json(next_geometry),
            _json(next_style),
            timestamp,
            artwork_id,
            object_id,
        ),
    )
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    _commit(connection, commit)
    return get_object(connection, artwork_id, object_id)


def delete_object(connection: sqlite3.Connection, artwork_id: str, object_id: str, *, commit: bool = True) -> DrawingObject:
    current = get_object(connection, artwork_id, object_id)
    timestamp = now_iso()
    connection.execute(
        "DELETE FROM drawing_objects WHERE artwork_id = ? AND id = ?",
        (artwork_id, object_id),
    )
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    _commit(connection, commit)
    return current


def delete_all_objects(connection: sqlite3.Connection, artwork_id: str, *, commit: bool = True) -> list[DrawingObject]:
    current_objects = get_artwork(connection, artwork_id).objects
    timestamp = now_iso()
    connection.execute("DELETE FROM drawing_objects WHERE artwork_id = ?", (artwork_id,))
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    _commit(connection, commit)
    return current_objects


def save_version(connection: sqlite3.Connection, artwork_id: str, *, commit: bool = True) -> None:
    artwork = get_artwork(connection, artwork_id)
    row = connection.execute(
        "SELECT COALESCE(MAX(version_no), 0) + 1 AS version_no FROM artwork_versions WHERE artwork_id = ?",
        (artwork_id,),
    ).fetchone()
    connection.execute(
        """
        INSERT INTO artwork_versions (id, artwork_id, version_no, object_snapshot_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id(),
            artwork_id,
            int(row["version_no"]),
            _json([obj.model_dump() for obj in artwork.objects]),
            now_iso(),
        ),
    )
    _commit(connection, commit)


def record_operation(
    connection: sqlite3.Connection,
    artwork_id: str,
    operation_type: str,
    payload: dict[str, Any],
    inverse_payload: dict[str, Any],
    status: str = "applied",
    command_group_id: str | None = None,
    operation_index: int = 0,
    commit: bool = True,
) -> str:
    operation_id = new_id()
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO operations
            (id, artwork_id, command_group_id, operation_index, operation_type, payload_json, inverse_payload_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            artwork_id,
            command_group_id,
            operation_index,
            operation_type,
            _json(payload),
            _json(inverse_payload),
            status,
            timestamp,
            timestamp,
        ),
    )
    _commit(connection, commit)
    return operation_id


def get_last_operation(connection: sqlite3.Connection, artwork_id: str, status: str) -> sqlite3.Row | None:
    order_by = "updated_at DESC, rowid DESC" if status == "undone" else "created_at DESC, rowid DESC"
    return connection.execute(
        f"""
        SELECT * FROM operations
        WHERE artwork_id = ? AND status = ?
        ORDER BY {order_by}
        LIMIT 1
        """,
        (artwork_id, status),
    ).fetchone()


def list_operation_group(connection: sqlite3.Connection, artwork_id: str, command_group_id: str, status: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM operations
        WHERE artwork_id = ? AND command_group_id = ? AND status = ?
        ORDER BY operation_index ASC, created_at ASC, rowid ASC
        """,
        (artwork_id, command_group_id, status),
    ).fetchall()


def mark_operation_status(connection: sqlite3.Connection, operation_id: str, status: str, *, commit: bool = True) -> None:
    connection.execute(
        "UPDATE operations SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), operation_id),
    )
    _commit(connection, commit)


def clear_redo_stack(connection: sqlite3.Connection, artwork_id: str, *, commit: bool = True) -> None:
    connection.execute("DELETE FROM operations WHERE artwork_id = ? AND status = 'undone'", (artwork_id,))
    _commit(connection, commit)


def get_latest_voice_log_by_status(connection: sqlite3.Connection, artwork_id: str, status: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM voice_command_logs
        WHERE artwork_id = ? AND status = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (artwork_id, status),
    ).fetchone()


def mark_voice_log_status(connection: sqlite3.Connection, log_id: str, status: str, *, error_message: str | None = None) -> None:
    connection.execute(
        "UPDATE voice_command_logs SET status = ?, error_message = ? WHERE id = ?",
        (status, error_message, log_id),
    )
    connection.commit()


def record_voice_log(
    connection: sqlite3.Connection,
    *,
    artwork_id: str | None,
    raw_transcript: str,
    normalized_text: str,
    parse_result: dict[str, Any],
    confidence: float,
    status: str,
    error_message: str | None,
    latency: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO voice_command_logs
            (id, artwork_id, raw_transcript, normalized_text, parse_result_json, confidence, status, error_message, latency_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id(),
            artwork_id,
            raw_transcript,
            normalized_text,
            _json(parse_result),
            confidence,
            status,
            error_message,
            _json(latency),
            now_iso(),
        ),
    )
    connection.commit()


def list_voice_latency_logs(connection: sqlite3.Connection, artwork_id: str | None = None, *, limit: int = 200) -> list[sqlite3.Row]:
    if artwork_id:
        return connection.execute(
            """
            SELECT status, latency_json, created_at
            FROM voice_command_logs
            WHERE artwork_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (artwork_id, limit),
        ).fetchall()
    return connection.execute(
        """
        SELECT status, latency_json, created_at
        FROM voice_command_logs
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
