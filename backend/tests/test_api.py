from __future__ import annotations

import os
import sqlite3

from fastapi.testclient import TestClient


SAMPLE_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _seed_drawing_object(artwork_id: str, obj: dict) -> None:
    from app.database import connect_db
    from app.drawing_engine import apply_operation
    from app.schemas import OperationRequest

    with connect_db(os.environ["AI_PAINTING_DB"]) as connection:
        apply_operation(connection, artwork_id, OperationRequest(operation_type="add_object", payload={"object": obj}))


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

    async def fake_plan_with_drawing_agent(_: str, *, rule_plan=None):
        nonlocal called
        called = True
        raise AssertionError("voice noise should not call MiMo")

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_drawing_agent", fake_plan_with_drawing_agent)

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


def test_agent_living_room_command_executes_complex_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个温馨客厅，有沙发、茶几、窗户和落地灯"})

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert len(body["artwork"]["objects"]) == 14
    semantic_tags = [tag for item in body["artwork"]["objects"] for tag in item["semantic_tags"]]
    assert "sofa" in semantic_tags
    assert "coffee_table" in semantic_tags
    assert "floor_lamp" in semantic_tags


def test_agent_edit_command_updates_existing_semantic_objects_and_undoes_as_group(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    create_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个温馨客厅，有沙发、茶几、窗户和落地灯"})
    assert create_response.status_code == 200
    before_sofas = [obj for obj in create_response.json()["artwork"]["objects"] if "sofa" in obj["semantic_tags"]]
    before_x = {obj["name"]: obj["geometry"].get("x") for obj in before_sofas if "x" in obj["geometry"]}

    edit_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把客厅的沙发改成绿色并向右移动一点"})

    assert edit_response.status_code == 200
    body = edit_response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert [operation["operation_type"] for operation in body["plan"]["operations"]] == ["set_style_many", "move_many"]
    edited_sofas = [obj for obj in body["artwork"]["objects"] if "sofa" in obj["semantic_tags"]]
    assert edited_sofas
    assert all(obj["style"]["fill"] == "#16a34a" for obj in edited_sofas)
    for obj in edited_sofas:
        if obj["name"] in before_x:
            assert obj["geometry"]["x"] == before_x[obj["name"]] + 20

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    restored_sofas = [obj for obj in undo_response.json()["artwork"]["objects"] if "sofa" in obj["semantic_tags"]]
    assert all(obj["style"]["fill"] != "#16a34a" for obj in restored_sofas)
    for obj in restored_sofas:
        if obj["name"] in before_x:
            assert obj["geometry"]["x"] == before_x[obj["name"]]


def test_agent_query_dsl_edits_relative_target_and_undoes(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    create_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个房子 红色屋顶 蓝色门 两扇窗户"})
    assert create_response.status_code == 200
    before_objects = create_response.json()["artwork"]["objects"]
    before_door = next(obj for obj in before_objects if "house.door" in obj["semantic_tags"])
    roof = next(obj for obj in before_objects if "house.roof" in obj["semantic_tags"])

    edit_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把屋顶下面的门改成绿色"})

    assert edit_response.status_code == 200
    body = edit_response.json()
    assert body["plan"]["planner_source"] == "agent"
    edited_door = next(obj for obj in body["artwork"]["objects"] if "house.door" in obj["semantic_tags"])
    edited_roof = next(obj for obj in body["artwork"]["objects"] if "house.roof" in obj["semantic_tags"])
    assert edited_door["style"]["fill"] == "#16a34a"
    assert edited_roof["style"]["fill"] == roof["style"]["fill"]

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    restored_door = next(obj for obj in undo_response.json()["artwork"]["objects"] if "house.door" in obj["semantic_tags"])
    assert restored_door["style"]["fill"] == before_door["style"]["fill"]


def test_agent_query_dsl_moves_warm_small_objects_only(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个红色圆形在左边 半径二十"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个黄色圆形在中间 半径二十"})
    client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个蓝色圆形在右边 半径二十"})
    before_objects = client.get(f"/api/artworks/{artwork_id}").json()["objects"]
    before_y = {obj["style"]["fill"]: obj["geometry"]["cy"] for obj in before_objects}

    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把所有暖色小物件向上移动一点"})

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    moved_objects = body["artwork"]["objects"]
    after_y = {obj["style"]["fill"]: obj["geometry"]["cy"] for obj in moved_objects}
    assert after_y["#dc2626"] == before_y["#dc2626"] - 20
    assert after_y["#facc15"] == before_y["#facc15"] - 20
    assert after_y["#2563eb"] == before_y["#2563eb"]


def test_group_query_moves_entire_sofa_including_arms(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    create_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "画一个温馨客厅，有沙发、茶几、窗户和落地灯"})
    assert create_response.status_code == 200
    before_sofa_parts = [obj for obj in create_response.json()["artwork"]["objects"] if obj["group_id"] == "sofa"]
    before_x = {obj["name"]: obj["geometry"].get("x") for obj in before_sofa_parts if "x" in obj["geometry"]}
    assert {"左扶手", "右扶手"}.issubset(before_x)

    move_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把整个沙发向右移动一点"})

    assert move_response.status_code == 200
    body = move_response.json()
    assert body["plan"]["planner_source"] == "agent"
    moved_sofa_parts = [obj for obj in body["artwork"]["objects"] if obj["group_id"] == "sofa"]
    for obj in moved_sofa_parts:
        if obj["name"] in before_x:
            assert obj["geometry"]["x"] == before_x[obj["name"]] + 20

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    restored_sofa_parts = [obj for obj in undo_response.json()["artwork"]["objects"] if obj["group_id"] == "sofa"]
    for obj in restored_sofa_parts:
        if obj["name"] in before_x:
            assert obj["geometry"]["x"] == before_x[obj["name"]]


def test_group_query_recolors_second_tree_group(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    create_response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个温馨的小屋 左边有两棵树 右边有一条弯曲小路 天空有三朵云"},
    )
    assert create_response.status_code == 200
    before_objects = create_response.json()["artwork"]["objects"]
    before_left_tree = [obj for obj in before_objects if obj["group_id"] == "tree-left"]
    before_far_tree = [obj for obj in before_objects if obj["group_id"] == "tree-far"]
    assert len(before_left_tree) == 2
    assert len(before_far_tree) == 2

    edit_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把左边第二棵树改成黄色"})

    assert edit_response.status_code == 200
    body = edit_response.json()
    assert body["plan"]["planner_source"] == "agent"
    edited_left_tree = [obj for obj in body["artwork"]["objects"] if obj["group_id"] == "tree-left"]
    edited_far_tree = [obj for obj in body["artwork"]["objects"] if obj["group_id"] == "tree-far"]
    assert all(obj["style"]["fill"] == "#facc15" for obj in edited_left_tree)
    assert any(obj["style"]["fill"] != "#facc15" for obj in edited_far_tree)

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    restored_left_tree = [obj for obj in undo_response.json()["artwork"]["objects"] if obj["group_id"] == "tree-left"]
    assert [obj["style"]["fill"] for obj in restored_left_tree] == [obj["style"]["fill"] for obj in before_left_tree]


def test_agent_flowchart_command_executes_diagram_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个语音绘图流程图，从用户语音到ASR，再到规划器，最后到画布执行"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert body["plan"]["scene_plan"]["steps"][0]["target"]["domain"] == "diagram_scene"
    objects = body["artwork"]["objects"]
    assert len(objects) == 12
    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 4
    assert object_types.count("text") == 5
    assert object_types.count("arrow") == 3
    semantic_tags = [tag for item in objects for tag in item["semantic_tags"]]
    assert "diagram.node" in semantic_tags
    assert "diagram.connector" in semantic_tags


def test_agent_infographic_command_executes_graphic_design_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个销售增长信息图，包含营收、转化率、复购率和三个月柱状图"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert body["plan"]["scene_plan"]["steps"][0]["target"]["domain"] == "infographic_scene"
    objects = body["artwork"]["objects"]
    assert len(objects) == 20
    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 7
    assert object_types.count("text") == 11
    assert object_types.count("line") == 2
    semantic_tags = [tag for item in objects for tag in item["semantic_tags"]]
    assert "infographic.metric_card" in semantic_tags
    assert "infographic.bar" in semantic_tags
    assert "bar_chart" in semantic_tags


def test_agent_poster_command_executes_graphic_design_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个AI语音绘图新品发布海报，突出主标题、产品视觉、三个卖点和立即体验按钮"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert body["plan"]["scene_plan"]["steps"][0]["target"]["domain"] == "poster_scene"
    objects = body["artwork"]["objects"]
    assert len(objects) == 20
    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 6
    assert object_types.count("text") == 8
    assert object_types.count("circle") == 4
    assert object_types.count("ellipse") == 1
    assert object_types.count("path") == 1
    semantic_tags = [tag for item in objects for tag in item["semantic_tags"]]
    assert "poster.headline" in semantic_tags
    assert "poster.hero" in semantic_tags
    assert "poster.cta" in semantic_tags
    assert "poster.feature_text" in semantic_tags


def test_agent_ui_wireframe_command_executes_product_design_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个语音绘图产品的UI草图，包含侧边导航、顶部栏、搜索框、主卡片、趋势图和新建作品按钮"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert body["plan"]["scene_plan"]["steps"][0]["target"]["domain"] == "ui_wireframe_scene"
    objects = body["artwork"]["objects"]
    assert len(objects) == 20
    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 13
    assert object_types.count("text") == 6
    assert object_types.count("circle") == 1
    semantic_tags = [tag for item in objects for tag in item["semantic_tags"]]
    assert "ui.sidebar" in semantic_tags
    assert "ui.search" in semantic_tags
    assert "ui.hero" in semantic_tags
    assert "ui.cta" in semantic_tags


def test_agent_org_chart_command_executes_hierarchy_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个产品团队组织结构图，包括负责人、产品组、设计组、研发组和执行角色"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert body["plan"]["scene_plan"]["steps"][0]["target"]["domain"] == "org_chart_scene"
    objects = body["artwork"]["objects"]
    assert len(objects) == 20
    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 8
    assert object_types.count("text") == 9
    assert object_types.count("line") == 3
    semantic_tags = [tag for item in objects for tag in item["semantic_tags"]]
    assert "org_chart.node" in semantic_tags
    assert "org_chart.connector" in semantic_tags
    assert "org_chart.department" in semantic_tags
    assert "org_chart.role" in semantic_tags


def test_agent_gantt_chart_command_executes_timeline_scene(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    response = client.post(
        f"/api/artworks/{artwork_id}/commands",
        json={"text": "画一个产品迭代项目排期甘特图，包含需求、设计、开发、测试和上线里程碑"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["planner_source"] == "agent"
    assert body["plan"]["scene_plan"]["steps"][0]["target"]["domain"] == "gantt_chart_scene"
    objects = body["artwork"]["objects"]
    assert len(objects) == 20
    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 6
    assert object_types.count("text") == 11
    assert object_types.count("line") == 2
    assert object_types.count("circle") == 1
    semantic_tags = [tag for item in objects for tag in item["semantic_tags"]]
    assert "gantt_chart.timeline" in semantic_tags
    assert "gantt_chart.task_bar" in semantic_tags
    assert "gantt_chart.milestone" in semantic_tags
    assert "gantt_chart.legend" in semantic_tags


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

    undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert undo_response.status_code == 200
    assert undo_response.json()["artwork"]["objects"] == []

    redo_response = client.post(f"/api/artworks/{artwork_id}/redo")
    assert redo_response.status_code == 200
    redone_objects = redo_response.json()["artwork"]["objects"]
    assert len(redone_objects) == 3
    assert [obj["name"] for obj in redone_objects] == ["星星1", "星星2", "星星3"]


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
    assert not any(obj["style"]["fill"] == "#16a34a" for obj in undone_objects)
    assert len([obj for obj in undone_objects if obj["style"]["fill"] == "#2563eb"]) == 2
    assert len([obj for obj in undone_objects if obj["style"]["fill"] == "#dc2626"]) == 1
    assert all((obj["geometry"].get("cy") == 384 or obj["geometry"].get("y") == 314) for obj in undone_objects)

    redo_response = client.post(f"/api/artworks/{artwork_id}/redo")
    assert redo_response.status_code == 200
    redone_objects = redo_response.json()["artwork"]["objects"]
    assert len([obj for obj in redone_objects if obj["style"]["fill"] == "#16a34a"]) == 2
    assert all((obj["geometry"].get("cy") == 364 or obj["geometry"].get("y") == 294) for obj in redone_objects)

    client.post(f"/api/artworks/{artwork_id}/undo")

    second_undo_response = client.post(f"/api/artworks/{artwork_id}/undo")
    assert second_undo_response.status_code == 200
    restored_objects = second_undo_response.json()["artwork"]["objects"]
    assert len(restored_objects) == 2
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


def test_voice_command_edits_tree_near_door(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    _seed_drawing_object(
        artwork_id,
        {
            "type": "rect",
            "name": "蓝色门",
            "semantic_tags": ["house.door"],
            "geometry": {"x": 480, "y": 430, "width": 80, "height": 120},
            "style": {"fill": "#2563eb", "stroke": "#1e3a8a", "strokeWidth": 2},
        },
    )
    for name, group_id, object_type, geometry in [
        ("近树树干", "tree-near", "rect", {"x": 620, "y": 430, "width": 35, "height": 110}),
        ("近树树冠", "tree-near", "circle", {"cx": 638, "cy": 385, "radius": 70}),
        ("远树树干", "tree-far", "rect", {"x": 100, "y": 450, "width": 30, "height": 90}),
        ("远树树冠", "tree-far", "circle", {"cx": 115, "cy": 405, "radius": 55}),
    ]:
        _seed_drawing_object(
            artwork_id,
            {
                "type": object_type,
                "name": name,
                "group_id": group_id,
                "semantic_tags": ["tree"],
                "geometry": geometry,
                "style": {"fill": "#16a34a", "stroke": "#166534", "strokeWidth": 2},
            },
        )

    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把靠近门的那棵树改成黄色"})

    assert response.status_code == 200
    objects_by_name = {obj["name"]: obj for obj in response.json()["artwork"]["objects"]}
    assert objects_by_name["近树树干"]["style"]["fill"] == "#facc15"
    assert objects_by_name["近树树冠"]["style"]["fill"] == "#facc15"
    assert objects_by_name["远树树干"]["style"]["fill"] == "#16a34a"
    assert objects_by_name["远树树冠"]["style"]["fill"] == "#16a34a"


def test_voice_command_moves_image_covering_title(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    _seed_drawing_object(
        artwork_id,
        {
            "type": "text",
            "name": "主标题",
            "semantic_tags": ["poster.headline"],
            "geometry": {"x": 300, "y": 180, "fontSize": 50, "content": "主标题"},
            "style": {"fill": "#111827", "stroke": "#111827", "strokeWidth": 0},
            "z_index": 1,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "image",
            "name": "遮挡标题的图片",
            "semantic_tags": ["generated.image"],
            "geometry": {"x": 220, "y": 110, "width": 180, "height": 110, "src": SAMPLE_PNG_DATA_URL},
            "style": {"opacity": 1},
            "z_index": 2,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "image",
            "name": "右侧图片",
            "semantic_tags": ["generated.image"],
            "geometry": {"x": 620, "y": 110, "width": 180, "height": 110, "src": SAMPLE_PNG_DATA_URL},
            "style": {"opacity": 1},
            "z_index": 3,
        },
    )

    response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把挡住标题的图片向右移动一点"})

    assert response.status_code == 200
    objects_by_name = {obj["name"]: obj for obj in response.json()["artwork"]["objects"]}
    assert objects_by_name["遮挡标题的图片"]["geometry"]["x"] == 240
    assert objects_by_name["右侧图片"]["geometry"]["x"] == 620


def test_voice_command_edits_text_inside_card_and_button_on_title_row(client: TestClient) -> None:
    artwork_id = client.post("/api/artworks", json={}).json()["id"]
    _seed_drawing_object(
        artwork_id,
        {
            "type": "rect",
            "name": "主卡片",
            "semantic_tags": ["ui.hero"],
            "geometry": {"x": 180, "y": 140, "width": 360, "height": 220, "radius": 20},
            "style": {"fill": "#eff6ff", "stroke": "#93c5fd", "strokeWidth": 2},
            "z_index": 1,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "text",
            "name": "卡片内文字",
            "semantic_tags": ["ui.hero.title"],
            "geometry": {"x": 360, "y": 230, "fontSize": 36, "content": "卡片内文字"},
            "style": {"fill": "#111827", "stroke": "#111827", "strokeWidth": 0},
            "z_index": 2,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "text",
            "name": "卡片外文字",
            "semantic_tags": ["ui.footer"],
            "geometry": {"x": 740, "y": 230, "fontSize": 36, "content": "卡片外文字"},
            "style": {"fill": "#111827", "stroke": "#111827", "strokeWidth": 0},
            "z_index": 2,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "text",
            "name": "主标题",
            "semantic_tags": ["poster.headline"],
            "geometry": {"x": 240, "y": 500, "fontSize": 44, "content": "主标题"},
            "style": {"fill": "#111827", "stroke": "#111827", "strokeWidth": 0},
            "z_index": 5,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "rect",
            "name": "同一行按钮",
            "semantic_tags": ["poster.cta"],
            "geometry": {"x": 500, "y": 470, "width": 150, "height": 60, "radius": 18},
            "style": {"fill": "#2563eb", "stroke": "#1e3a8a", "strokeWidth": 2},
            "z_index": 6,
        },
    )
    _seed_drawing_object(
        artwork_id,
        {
            "type": "rect",
            "name": "错行按钮",
            "semantic_tags": ["poster.cta"],
            "geometry": {"x": 500, "y": 610, "width": 150, "height": 60, "radius": 18},
            "style": {"fill": "#2563eb", "stroke": "#1e3a8a", "strokeWidth": 2},
            "z_index": 6,
        },
    )

    text_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把卡片里的文字改成蓝色"})
    assert text_response.status_code == 200
    objects_by_name = {obj["name"]: obj for obj in text_response.json()["artwork"]["objects"]}
    assert objects_by_name["卡片内文字"]["style"]["fill"] == "#2563eb"
    assert objects_by_name["卡片外文字"]["style"]["fill"] == "#111827"

    button_response = client.post(f"/api/artworks/{artwork_id}/commands", json={"text": "把和标题同一行的按钮改成绿色"})
    assert button_response.status_code == 200
    objects_by_name = {obj["name"]: obj for obj in button_response.json()["artwork"]["objects"]}
    assert objects_by_name["同一行按钮"]["style"]["fill"] == "#16a34a"
    assert objects_by_name["错行按钮"]["style"]["fill"] == "#2563eb"


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
