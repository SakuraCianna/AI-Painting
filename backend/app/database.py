from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path


DRAWING_OBJECT_COLUMNS: dict[str, str] = {
    "layer_id": "TEXT NOT NULL DEFAULT 'base'",
    "group_id": "TEXT",
    "semantic_tags_json": "TEXT NOT NULL DEFAULT '[]'",
    "transform_json": "TEXT NOT NULL DEFAULT '{}'",
}

OPERATION_COLUMNS: dict[str, str] = {
    "command_group_id": "TEXT",
    "operation_index": "INTEGER NOT NULL DEFAULT 0",
}

ALLOWED_MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "drawing_objects": DRAWING_OBJECT_COLUMNS,
    "operations": OPERATION_COLUMNS,
}

SQLITE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_SQLITE_CACHE_SIZE_KIB = 8192
MIN_SQLITE_CACHE_SIZE_KIB = 1024
MAX_SQLITE_CACHE_SIZE_KIB = 65536


def get_database_path() -> str:
    return os.environ.get("AI_PAINTING_DB", str(Path("backend") / "data" / "ai_painting.sqlite3"))


def get_sqlite_cache_size_kib() -> int:
    raw_value = os.environ.get("AI_PAINTING_SQLITE_CACHE_SIZE_KIB")
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_SQLITE_CACHE_SIZE_KIB
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_SQLITE_CACHE_SIZE_KIB
    return max(MIN_SQLITE_CACHE_SIZE_KIB, min(parsed, MAX_SQLITE_CACHE_SIZE_KIB))


def connect_db(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or get_database_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA cache_size = {-get_sqlite_cache_size_kib()}")
    return connection


def init_db(path: str | None = None) -> None:
    with connect_db(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS artworks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                background TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS artwork_versions (
                id TEXT PRIMARY KEY,
                artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
                version_no INTEGER NOT NULL,
                object_snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drawing_objects (
                id TEXT PRIMARY KEY,
                artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                name TEXT,
                layer_id TEXT NOT NULL DEFAULT 'base',
                group_id TEXT,
                semantic_tags_json TEXT NOT NULL DEFAULT '[]',
                transform_json TEXT NOT NULL DEFAULT '{}',
                geometry_json TEXT NOT NULL,
                style_json TEXT NOT NULL,
                z_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
                command_group_id TEXT,
                operation_index INTEGER NOT NULL DEFAULT 0,
                operation_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                inverse_payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS voice_command_logs (
                id TEXT PRIMARY KEY,
                artwork_id TEXT REFERENCES artworks(id) ON DELETE SET NULL,
                raw_transcript TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                parse_result_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                latency_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_drawing_objects_artwork_z
                ON drawing_objects (artwork_id, z_index, created_at);
            CREATE INDEX IF NOT EXISTS idx_drawing_objects_artwork_type
                ON drawing_objects (artwork_id, type);
            CREATE INDEX IF NOT EXISTS idx_operations_artwork_status_created
                ON operations (artwork_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_voice_logs_artwork_created
                ON voice_command_logs (artwork_id, created_at);
            """
        )
        _ensure_drawing_object_columns(connection)
        _ensure_operation_columns(connection)
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_drawing_objects_artwork_layer
                ON drawing_objects (artwork_id, layer_id, z_index);
            CREATE INDEX IF NOT EXISTS idx_drawing_objects_artwork_group
                ON drawing_objects (artwork_id, group_id, z_index);
            CREATE INDEX IF NOT EXISTS idx_operations_artwork_group_status
                ON operations (artwork_id, command_group_id, status, operation_index);
            """
        )


def _ensure_drawing_object_columns(connection: sqlite3.Connection) -> None:
    _ensure_columns(connection, "drawing_objects", DRAWING_OBJECT_COLUMNS)


def _ensure_operation_columns(connection: sqlite3.Connection) -> None:
    _ensure_columns(connection, "operations", OPERATION_COLUMNS)


def _ensure_columns(connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    allowed_columns = ALLOWED_MIGRATION_COLUMNS.get(table_name)
    if allowed_columns is None:
        raise ValueError(f"不允许的迁移表: {table_name}")
    for column_name, column_definition in columns.items():
        if allowed_columns.get(column_name) != column_definition:
            raise ValueError(f"不允许的迁移列: {table_name}.{column_name}")
    quoted_table = _quote_sqlite_identifier(table_name)
    existing_columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()}
    for column_name, column_definition in columns.items():
        if column_name not in existing_columns:
            quoted_column = _quote_sqlite_identifier(column_name)
            connection.execute(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {column_definition}")


def _quote_sqlite_identifier(identifier: str) -> str:
    if not SQLITE_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"不允许的数据库标识符: {identifier}")
    return f'"{identifier}"'


def get_db() -> Iterator[sqlite3.Connection]:
    connection = connect_db()
    try:
        yield connection
    finally:
        connection.close()
