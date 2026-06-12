from __future__ import annotations

from app.agent.graph import run_agent_graph
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
