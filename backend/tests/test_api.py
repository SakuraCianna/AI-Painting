from __future__ import annotations

import os
import sqlite3

from fastapi.testclient import TestClient


SAMPLE_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


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
    assert body["metrics"]["planner_source"] == body["plan"]["planner_source"]
    assert body["metrics"]["planner_total_ms"] >= 0
    assert body["metrics"]["execute_ms"] >= 0
    assert body["metrics"]["total_ms"] >= body["metrics"]["planner_total_ms"]


def test_latency_metrics_api_summarizes_voice_command_logs(client: TestClient) -> None:
    from app.database import connect_db
    from app.repositories import record_voice_log

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    latency_samples = [100, 200, 300, 400]

    with connect_db(os.environ["AI_PAINTING_DB"]) as connection:
        for index, total_ms in enumerate(latency_samples):
            record_voice_log(
                connection,
                artwork_id=artwork_id,
                raw_transcript=f"样本 {index}",
                normalized_text=f"样本 {index}",
                parse_result={},
                confidence=0.9,
                status="success" if index < 3 else "failed",
                error_message=None if index < 3 else "测试失败样本",
                latency={
                    "rule_parse_ms": 10 + index,
                    "planner_total_ms": total_ms / 2,
                    "execute_ms": total_ms / 4,
                    "total_ms": total_ms,
                    "planner_source": "rules",
                },
            )

    response = client.get(f"/api/metrics/latency?artwork_id={artwork_id}&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["artwork_id"] == artwork_id
    assert body["sample_count"] == 4
    assert body["success_count"] == 3
    assert body["failed_count"] == 1
    assert body["planner_sources"] == {"rules": 4}
    assert body["metrics"]["total_ms"]["average_ms"] == 250
    assert body["metrics"]["total_ms"]["p50_ms"] == 200
    assert body["metrics"]["total_ms"]["p75_ms"] == 300
    assert body["metrics"]["total_ms"]["p95_ms"] == 400


def test_latency_metrics_api_returns_404_for_missing_artwork(client: TestClient) -> None:
    response = client.get("/api/metrics/latency?artwork_id=missing-artwork")

    assert response.status_code == 404


def test_voice_noise_command_requires_clarification_without_mimo(client: TestClient, monkeypatch) -> None:
    from app import main

    called = False

    async def fake_plan_with_mimo(_: str):
        nonlocal called
        called = True
        raise AssertionError("voice noise should not call MiMo")

    monkeypatch.setenv("AI_PAINTING_ENABLE_LLM_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_mimo", fake_plan_with_mimo)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "嗯。"})

    assert response.status_code == 200
    body = response.json()
    assert called is False
    assert body["message"] == "我听到的是口头语或噪声, 请直接说要画什么、怎么改或要执行的操作。"
    assert body["plan"]["requires_confirmation"] is True
    assert body["plan"]["operations"] == []
    assert body["plan"]["planner_source"] == "rules"
    assert body["artwork"]["objects"] == []


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

    replace_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把窗户改成圆形"})
    assert replace_response.status_code == 200
    replaced_windows = [obj for obj in replace_response.json()["artwork"]["objects"] if "house.window" in obj["semantic_tags"]]
    assert [obj["type"] for obj in replaced_windows] == ["circle", "circle"]

    undo_replace_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_replace_response.status_code == 200
    restored_windows = [obj for obj in undo_replace_response.json()["artwork"]["objects"] if "house.window" in obj["semantic_tags"]]
    assert [obj["type"] for obj in restored_windows] == ["rect", "rect"]


def test_house_command_respects_component_color_words(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个房子，红色门，两个窗户。"})

    assert response.status_code == 200
    objects = response.json()["artwork"]["objects"]
    door = next(obj for obj in objects if "house.door" in obj["semantic_tags"])
    windows = [obj for obj in objects if "house.window" in obj["semantic_tags"]]
    assert door["style"]["fill"] == "#dc2626"
    assert len(windows) == 2


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
    assert body["plan"]["requires_confirmation"] is False
    assert len(body["plan"]["operations"]) == 14
    assert len(body["artwork"]["objects"]) == 14
    assert body["plan"]["planner_source"] == "rules"
    assert body["metrics"]["planner_total_ms"] >= 0


def test_text_to_image_placeholder_generates_editable_image_object(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "生成一张人物肖像画"})

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["operations"][0]["operation_type"] == "add_object"
    image_object = body["artwork"]["objects"][0]
    assert image_object["type"] == "image"
    assert image_object["geometry"]["src"].startswith("data:image/svg+xml;base64,")
    assert image_object["geometry"]["provider"] == "placeholder"


def test_polish_image_placeholder_uses_canvas_snapshot(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_PROVIDER", "placeholder")
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "精修我的图片", "canvas_image_data_url": SAMPLE_PNG_DATA_URL},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["operations"][0]["operation_type"] == "add_object"
    image_object = body["artwork"]["objects"][0]
    assert image_object["type"] == "image"
    assert image_object["name"] == "精修版本"
    assert image_object["geometry"]["provider"] == "placeholder"
    assert "polished.image" in image_object["semantic_tags"]


def test_left_window_spatial_selector_scales_only_one_window(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个房子 红色屋顶 蓝色门 两扇窗户"})

    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把左边窗户改大一点"})

    assert response.status_code == 200
    windows = [obj for obj in response.json()["artwork"]["objects"] if "house.window" in obj["semantic_tags"]]
    assert [obj["geometry"]["width"] for obj in windows] == [76.8, 64]


def test_clear_canvas_confirmation_executes_and_preserves_undo_redo_history(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色圆形在左边"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个黄色星星在右边"})

    clear_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "清空画布"})

    assert clear_response.status_code == 200
    clear_body = clear_response.json()
    assert clear_body["plan"]["requires_confirmation"] is True
    assert clear_body["plan"]["operations"][0]["operation_type"] == "clear_canvas"
    assert len(clear_body["artwork"]["objects"]) == 2
    assert clear_body["metrics"]["execute_ms"] == 0

    confirm_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "确认清空"})

    assert confirm_response.status_code == 200
    confirm_body = confirm_response.json()
    assert confirm_body["message"] == "已清空画布"
    assert confirm_body["plan"]["requires_confirmation"] is False
    assert confirm_body["plan"]["planner_source"] == "confirmation"
    assert confirm_body["artwork"]["objects"] == []

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    restored_objects = undo_response.json()["artwork"]["objects"]
    assert [obj["type"] for obj in restored_objects] == ["circle", "star"]

    redo_response = client.post(f"/api/artworks/{artwork_id}/redo")
    assert redo_response.status_code == 200
    assert redo_response.json()["artwork"]["objects"] == []

    connection = sqlite3.connect(os.environ["AI_PAINTING_DB"])
    connection.row_factory = sqlite3.Row
    operations = connection.execute(
        "SELECT operation_type, status FROM operations WHERE artwork_id = ? ORDER BY created_at, rowid",
        (artwork_id,),
    ).fetchall()
    logs = connection.execute(
        "SELECT raw_transcript, status FROM voice_command_logs WHERE artwork_id = ? ORDER BY created_at, rowid",
        (artwork_id,),
    ).fetchall()
    connection.close()

    assert operations[-1]["operation_type"] == "clear_canvas"
    assert operations[-1]["status"] == "applied"
    assert ("清空画布", "confirmed") in [(row["raw_transcript"], row["status"]) for row in logs]
    assert ("确认清空", "success") in [(row["raw_transcript"], row["status"]) for row in logs]


def test_cancel_clear_canvas_confirmation_keeps_objects(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色圆形"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "清空画布"})

    cancel_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "取消清空"})

    assert cancel_response.status_code == 200
    body = cancel_response.json()
    assert body["message"] == "已取消清空画布"
    assert len(body["artwork"]["objects"]) == 1

    connection = sqlite3.connect(os.environ["AI_PAINTING_DB"])
    connection.row_factory = sqlite3.Row
    logs = connection.execute(
        "SELECT raw_transcript, status FROM voice_command_logs WHERE artwork_id = ? ORDER BY created_at, rowid",
        (artwork_id,),
    ).fetchall()
    connection.close()

    assert ("清空画布", "canceled") in [(row["raw_transcript"], row["status"]) for row in logs]
    assert ("取消清空", "canceled") in [(row["raw_transcript"], row["status"]) for row in logs]
