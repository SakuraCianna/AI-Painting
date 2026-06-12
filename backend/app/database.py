from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path


def get_database_path() -> str:
    return os.environ.get("AI_PAINTING_DB", str(Path("backend") / "data" / "ai_painting.sqlite3"))


def connect_db(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or get_database_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
                geometry_json TEXT NOT NULL,
                style_json TEXT NOT NULL,
                z_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
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
            """
        )


def get_db() -> Iterator[sqlite3.Connection]:
    connection = connect_db()
    try:
        yield connection
    finally:
        connection.close()
