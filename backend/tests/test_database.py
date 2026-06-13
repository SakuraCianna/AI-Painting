from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import init_db


def test_init_db_migrates_old_drawing_object_metadata_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE artworks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            background TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE drawing_objects (
            id TEXT PRIMARY KEY,
            artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            name TEXT,
            geometry_json TEXT NOT NULL,
            style_json TEXT NOT NULL,
            z_index INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE operations (
            id TEXT PRIMARY KEY,
            artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
            operation_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            inverse_payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.close()

    init_db(str(db_path))

    migrated = sqlite3.connect(db_path)
    object_columns = {row[1] for row in migrated.execute("PRAGMA table_info(drawing_objects)").fetchall()}
    operation_columns = {row[1] for row in migrated.execute("PRAGMA table_info(operations)").fetchall()}
    migrated.close()
    assert {"layer_id", "group_id", "semantic_tags_json", "transform_json"}.issubset(object_columns)
    assert {"command_group_id", "operation_index"}.issubset(operation_columns)
