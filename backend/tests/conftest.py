from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("AI_PAINTING_DB", str(db_path))

    from app.database import init_db
    from app.main import app

    init_db(str(db_path))
    with TestClient(app) as test_client:
        yield test_client
