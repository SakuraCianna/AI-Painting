from __future__ import annotations

import base64

from app import plantuml_renderer
from app.agent.plantuml_builder import build_plantuml_scene_graph
from app.plantuml_editor import edit_plantuml_geometry
from app.plantuml_renderer import validate_plantuml_source


def _install_fake_plantuml_server(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.setenv("AI_PAINTING_PLANTUML_SERVER_URL", "https://plantuml.example.test")
    plantuml_renderer._render_plantuml_cached.cache_clear()

    class Response:
        text = '<svg xmlns="http://www.w3.org/2000/svg"><text>plantuml-ok</text></svg>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, timeout: float) -> Response:
        assert url.startswith("https://plantuml.example.test/svg/")
        assert timeout == 8.0
        return Response()

    monkeypatch.setattr(plantuml_renderer.httpx, "get", fake_get)


def _decode_svg(data_url: str) -> str:
    prefix = "data:image/svg+xml;base64,"
    assert data_url.startswith(prefix)
    return base64.b64decode(data_url[len(prefix) :]).decode("utf-8")


def _assert_source_contract(source: str) -> None:
    cleaned = validate_plantuml_source(source)
    first_line = cleaned.splitlines()[0].strip().lower()
    end_marker = {
        "@startuml": "@enduml",
        "@startwbs": "@endwbs",
        "@startgantt": "@endgantt",
    }[first_line]
    assert cleaned.lower().count(first_line) == 1
    assert cleaned.lower().count(end_marker) == 1
    assert cleaned.lower().endswith(end_marker)
    assert "!include" not in cleaned.lower()
    assert "!import" not in cleaned.lower()


def _assert_rendered_plantuml_geometry(geometry: dict[str, object], expected_type: str) -> None:
    assert geometry["diagramType"] == expected_type
    assert geometry["renderMode"] == "server"
    assert geometry["renderError"] is None
    source = str(geometry["source"])
    _assert_source_contract(source)
    svg = _decode_svg(str(geometry["src"]))
    assert "<svg" in svg
    assert "plantuml-ok" in svg


def _plantuml_geometry_for(text: str) -> dict[str, object]:
    graph = build_plantuml_scene_graph(text)
    assert graph is not None
    assert len(graph.objects) == 1
    obj = graph.objects[0]
    assert obj.type == "plantuml"
    return obj.geometry


def test_all_supported_plantuml_templates_render_through_server(monkeypatch) -> None:  # noqa: ANN001
    _install_fake_plantuml_server(monkeypatch)
    cases = [
        ("画一个语音绘图流程图，从用户语音到ASR，再到规划器，最后到画布执行", "activity"),
        ("画一个AI绘图系统架构图，包含前端、后端、ASR服务、Agent规划器、SQLite数据库和图像生成服务", "component"),
        ("画一个用户订单er图，包含用户、订单、商品和支付", "er"),
        ("画一个产品团队组织结构图，包括负责人、产品组、设计组、研发组和执行角色", "org"),
        ("画一个产品迭代项目排期甘特图，包含需求、设计、开发、测试和上线里程碑", "gantt"),
        ("画一个泳道图，泳道包括产品、设计、研发、测试，节点包括需求评审、原型设计、开发联调、验收发布", "swimlane"),
        ("画一个语音绘图调用时序图", "sequence"),
        ("画一个绘图 Agent UML 类图", "class"),
    ]

    for text, expected_type in cases:
        geometry = _plantuml_geometry_for(text)
        _assert_rendered_plantuml_geometry(geometry, expected_type)


def test_plantuml_edits_keep_sources_renderable(monkeypatch) -> None:  # noqa: ANN001
    _install_fake_plantuml_server(monkeypatch)

    flow_geometry = _plantuml_geometry_for("画一个语音绘图流程图，从用户语音到ASR，再到规划器，最后到画布执行")
    renamed_flow = edit_plantuml_geometry(flow_geometry, {"action": "rename", "old_text": "ASR识别", "new_text": "语音识别"})
    _assert_rendered_plantuml_geometry(renamed_flow, "activity")

    gantt_geometry = _plantuml_geometry_for("画一个产品迭代项目排期甘特图，包含需求、设计、开发、测试和上线里程碑")
    updated_gantt = edit_plantuml_geometry(gantt_geometry, {"action": "update_gantt_task", "task_name": "开发", "duration_days": 8})
    _assert_rendered_plantuml_geometry(updated_gantt, "gantt")
    assert "[开发] lasts 8 days" in updated_gantt["source"]

    swimlane_geometry = _plantuml_geometry_for("画一个泳道图，包含销售、运营和交付")
    edited_swimlane = edit_plantuml_geometry(swimlane_geometry, {"action": "add_swimlane", "lane_name": "法务", "step_name": "合同审核"})
    _assert_rendered_plantuml_geometry(edited_swimlane, "swimlane")
    assert "|法务|" in edited_swimlane["source"]

    er_geometry = _plantuml_geometry_for("画一个用户订单er图，包含用户、订单、商品和支付")
    reconnected_er = edit_plantuml_geometry(
        er_geometry,
        {
            "action": "reconnect_relation",
            "relation_text": "用户和订单之间的关系",
            "source_entity": "用户",
            "target_entity": "订单",
            "new_source_entity": "用户",
            "new_target_entity": "支付",
            "new_label": "支付",
        },
    )
    _assert_rendered_plantuml_geometry(reconnected_er, "er")
    assert "entity_1 ||--o{ entity_4 : 支付" in reconnected_er["source"]
