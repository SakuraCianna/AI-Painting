from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .schemas import ArtworkCreateRequest, ArtworkResponse, DrawingObject


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def _json(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _loads(raw: str) -> Any:
    return json.loads(raw)


def row_to_object(row: sqlite3.Row) -> DrawingObject:
    return DrawingObject(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        geometry=_loads(row["geometry_json"]),
        style=_loads(row["style_json"]),
        z_index=row["z_index"],
    )


def create_artwork(connection: sqlite3.Connection, request: ArtworkCreateRequest) -> ArtworkResponse:
    artwork_id = new_id()
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO artworks (id, title, width, height, background, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (artwork_id, request.title, request.width, request.height, request.background, timestamp, timestamp),
    )
    connection.commit()
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
    connection.commit()
    return get_artwork(connection, artwork_id)


def get_next_z_index(connection: sqlite3.Connection, artwork_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(z_index), -1) + 1 AS next_z FROM drawing_objects WHERE artwork_id = ?",
        (artwork_id,),
    ).fetchone()
    return int(row["next_z"])


def add_object(connection: sqlite3.Connection, artwork_id: str, obj: dict[str, Any]) -> DrawingObject:
    timestamp = now_iso()
    object_id = obj.get("id") or new_id()
    z_index = int(obj.get("z_index", get_next_z_index(connection, artwork_id)))
    connection.execute(
        """
        INSERT INTO drawing_objects
            (id, artwork_id, type, name, geometry_json, style_json, z_index, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            object_id,
            artwork_id,
            obj["type"],
            obj.get("name"),
            _json(obj.get("geometry", {})),
            _json(obj.get("style", {})),
            z_index,
            timestamp,
            timestamp,
        ),
    )
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    connection.commit()
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


def update_object(
    connection: sqlite3.Connection,
    artwork_id: str,
    object_id: str,
    *,
    geometry: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
    name: str | None = None,
) -> DrawingObject:
    current = get_object(connection, artwork_id, object_id)
    next_geometry = {**current.geometry, **(geometry or {})}
    next_style = {**current.style, **(style or {})}
    timestamp = now_iso()
    connection.execute(
        """
        UPDATE drawing_objects
        SET name = ?, geometry_json = ?, style_json = ?, updated_at = ?
        WHERE artwork_id = ? AND id = ?
        """,
        (
            name if name is not None else current.name,
            _json(next_geometry),
            _json(next_style),
            timestamp,
            artwork_id,
            object_id,
        ),
    )
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    connection.commit()
    return get_object(connection, artwork_id, object_id)


def delete_object(connection: sqlite3.Connection, artwork_id: str, object_id: str) -> DrawingObject:
    current = get_object(connection, artwork_id, object_id)
    timestamp = now_iso()
    connection.execute(
        "DELETE FROM drawing_objects WHERE artwork_id = ? AND id = ?",
        (artwork_id, object_id),
    )
    connection.execute("UPDATE artworks SET updated_at = ? WHERE id = ?", (timestamp, artwork_id))
    connection.commit()
    return current


def save_version(connection: sqlite3.Connection, artwork_id: str) -> None:
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
    connection.commit()


def record_operation(
    connection: sqlite3.Connection,
    artwork_id: str,
    operation_type: str,
    payload: dict[str, Any],
    inverse_payload: dict[str, Any],
    status: str = "applied",
) -> str:
    operation_id = new_id()
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO operations
            (id, artwork_id, operation_type, payload_json, inverse_payload_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (operation_id, artwork_id, operation_type, _json(payload), _json(inverse_payload), status, timestamp, timestamp),
    )
    connection.commit()
    return operation_id


def get_last_operation(connection: sqlite3.Connection, artwork_id: str, status: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM operations
        WHERE artwork_id = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (artwork_id, status),
    ).fetchone()


def mark_operation_status(connection: sqlite3.Connection, operation_id: str, status: str) -> None:
    connection.execute(
        "UPDATE operations SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), operation_id),
    )
    connection.commit()


def clear_redo_stack(connection: sqlite3.Connection, artwork_id: str) -> None:
    connection.execute("DELETE FROM operations WHERE artwork_id = ? AND status = 'undone'", (artwork_id,))
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
