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


def test_complex_multi_star_plan_executes_as_one_voice_command(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画三颗黄色星星 从左到右变小"})
    assert response.status_code == 200
    objects = response.json()["artwork"]["objects"]
    assert len(objects) == 3
    assert [obj["name"] for obj in objects] == ["星星1", "星星2", "星星3"]
    assert objects[0]["geometry"]["outerRadius"] > objects[1]["geometry"]["outerRadius"] > objects[2]["geometry"]["outerRadius"]


def test_batch_recolor_move_and_undo(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色圆形在左边"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色矩形在右边"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个红色圆形在中间"})

    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "把所有蓝色图形改成绿色 然后整体向上移动一点"},
    )
    assert response.status_code == 200
    objects = response.json()["artwork"]["objects"]
    green_objects = [obj for obj in objects if obj["style"]["fill"] == "#16a34a"]
    assert len(green_objects) == 2
    assert all((obj["geometry"].get("cy") == 364 or obj["geometry"].get("y") == 294) for obj in objects)

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    undone_objects = undo_response.json()["artwork"]["objects"]
    assert any(obj["style"]["fill"] == "#16a34a" for obj in undone_objects)
    assert all((obj["geometry"].get("cy") == 384 or obj["geometry"].get("y") == 314) for obj in undone_objects)

    second_undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert second_undo_response.status_code == 200
    restored_objects = second_undo_response.json()["artwork"]["objects"]
    assert len([obj for obj in restored_objects if obj["style"]["fill"] == "#2563eb"]) == 2


def test_scale_latest_object(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色圆形在中间 半径一百"})
    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把它放大一倍"})
    assert response.status_code == 200
    assert response.json()["artwork"]["objects"][0]["geometry"]["radius"] == 200


def test_object_metadata_and_semantic_batch_scale(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]

    create_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个房子 红色屋顶 蓝色门 两扇窗户"})
    assert create_response.status_code == 200
    window_objects = [obj for obj in create_response.json()["artwork"]["objects"] if "house.window" in obj["semantic_tags"]]
    assert len(window_objects) == 2
    assert all(obj["layer_id"] == "middle" for obj in window_objects)
    assert all(obj["group_id"] == "house" for obj in window_objects)

    scale_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把房子的窗户都变大"})
    assert scale_response.status_code == 200
    scaled_windows = [obj for obj in scale_response.json()["artwork"]["objects"] if "house.window" in obj["semantic_tags"]]
    assert all(obj["geometry"]["width"] == 76.8 for obj in scaled_windows)
    assert all(obj["geometry"]["height"] == 76.8 for obj in scaled_windows)


def test_rename_latest_and_move_layer(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个黄色圆形 命名为太阳 放到前景层"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色矩形 放到前景层"})

    rename_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把它命名为标记块"})
    assert rename_response.status_code == 200
    objects = rename_response.json()["artwork"]["objects"]
    assert objects[-1]["name"] == "标记块"
    assert objects[-1]["layer_id"] == "foreground"

    move_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把前景层所有对象向右移动一点"})
    assert move_response.status_code == 200
    moved_objects = move_response.json()["artwork"]["objects"]
    assert moved_objects[0]["geometry"]["cx"] == 532
    assert moved_objects[1]["geometry"]["x"] == 422


def test_path_shapes_execute_and_move(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    polygon_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个绿色五边形在左边"})
    assert polygon_response.status_code == 200
    polygon = polygon_response.json()["artwork"]["objects"][0]
    assert polygon["type"] == "polygon"
    assert len(polygon["geometry"]["points"]) == 5

    path_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一条弯曲小路"})
    assert path_response.status_code == 200
    path = path_response.json()["artwork"]["objects"][1]
    assert path["type"] == "path"
    assert path["style"]["strokeWidth"] == 10

    move_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "向右移动二十像素"})
    assert move_response.status_code == 200
    moved_path = move_response.json()["artwork"]["objects"][1]
    assert moved_path["geometry"]["commands"][0]["x"] == path["geometry"]["commands"][0]["x"] + 20


def test_complex_scene_requires_clarification_without_partial_execution(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个温馨的小屋 左边有两棵树 右边有一条弯曲小路 天空有三朵云"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["requires_confirmation"] is True
    assert body["plan"]["operations"] == []
    assert body["plan"]["planner_source"] in {"rules", "rules_fallback"}
    assert body["artwork"]["objects"] == []
