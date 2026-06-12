from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_artwork_and_execute_voice_command(client: TestClient) -> None:
    create_response = client.post("/api/artworks", json={"title": "语音练习", "width": 1024, "height": 768, "background": "#ffffff"})
    assert create_response.status_code == 200
    artwork_id = create_response.json()["id"]

    command_response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个蓝色圆形在中间 半径一百"},
    )
    assert command_response.status_code == 200
    body = command_response.json()
    assert body["artwork"]["objects"][0]["type"] == "circle"
    assert body["artwork"]["objects"][0]["style"]["fill"] == "#2563eb"


def test_undo_and_redo(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个黄色星星在左边"})

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    assert undo_response.json()["artwork"]["objects"] == []

    redo_response = client.post(f"/api/artworks/{artwork_id}/redo")
    assert redo_response.status_code == 200
    assert redo_response.json()["artwork"]["objects"][0]["type"] == "star"
