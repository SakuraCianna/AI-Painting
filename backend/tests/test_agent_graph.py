from __future__ import annotations

import asyncio

from app.agent.graph import run_agent_graph, run_drawing_agent_graph
from app.agent.scene_graph import AgentSceneGraph, AgentSceneObject, AgentSceneRelation, AgentStyle


def test_agent_graph_repairs_geometry_layer_tags_and_relations() -> None:
    graph = AgentSceneGraph(
        intent="compose_scene",
        domain="test_scene",
        summary="测试修复场景",
        objects=[
            AgentSceneObject(
                object_id="box",
                type="rect",
                name="越界矩形",
                layer_id="invalid-layer",
                group_id="test-group",
                semantic_tags=[],
                geometry={"x": -120, "y": 900, "width": 5000, "height": -5, "radius": 12},
                style=AgentStyle(fill="#2563eb", stroke="#111827", strokeWidth=2, opacity=1),
            )
        ],
        relations=[
            AgentSceneRelation(subject="box", relation="left_of", target="missing"),
        ],
        confidence=0.78,
    )

    plan = run_agent_graph("画一个测试矩形", "画一个测试矩形", graph)
    obj = plan.operations[0].payload["object"]

    assert obj["layer_id"] == "middle"
    assert obj["geometry"]["x"] == 0
    assert obj["geometry"]["y"] == 768
    assert obj["geometry"]["width"] == 1024
    assert obj["geometry"]["height"] == 1
    assert "test_scene" in obj["semantic_tags"]
    assert "test-group" in obj["semantic_tags"]
    assert plan.scene_plan is not None
    assert plan.scene_plan.steps[0].target["relations"] == []


def test_agent_graph_requires_confirmation_for_high_risk_scene() -> None:
    graph = AgentSceneGraph(
        intent="clear_or_replace_scene",
        domain="vector_canvas",
        summary="高风险重绘计划",
        objects=[],
        relations=[],
        confidence=0.5,
        risk_level="high",
    )

    plan = run_agent_graph("清空并重绘", "清空并重绘", graph)

    assert plan.requires_confirmation is True
    assert plan.operations == []
    assert plan.risk_level == "high"
    assert plan.clarification_question is not None


def test_agent_graph_repairs_invalid_scene_with_model_repairer() -> None:
    broken_graph = AgentSceneGraph(
        intent="compose_scene",
        domain="office_scene",
        summary="缺少对象的办公室场景",
        objects=[],
        relations=[],
        confidence=0.62,
    )
    repair_errors: list[str] = []

    async def fake_repairer(text: str, scene_graph: AgentSceneGraph, validation_error: str) -> AgentSceneGraph:
        repair_errors.append(validation_error)
        return AgentSceneGraph(
            intent="compose_scene",
            domain=scene_graph.domain,
            summary=f"修复后的{text}",
            objects=[
                AgentSceneObject(
                    object_id="desk",
                    type="rect",
                    name="办公桌",
                    layer_id="middle",
                    group_id="office",
                    semantic_tags=["desk"],
                    geometry={"x": 280, "y": 430, "width": 360, "height": 110, "radius": 14},
                    style=AgentStyle(fill="#d6d3d1", stroke="#44403c", strokeWidth=3, opacity=1),
                )
            ],
            relations=[],
            confidence=0.78,
        )

    plan = asyncio.run(
        run_drawing_agent_graph(
            "画一个办公室场景",
            "画一个办公室场景",
            scene_graph=broken_graph,
            scene_graph_repairer=fake_repairer,
        )
    )

    assert repair_errors == ["SceneGraph 没有对象"]
    assert plan.planner_source == "agent"
    assert plan.operations[0].payload["object"]["name"] == "办公桌"
