from __future__ import annotations

import asyncio

from app.agent.planner import DrawingAgentError
from app.agent.scene_graph import AgentSceneGraph, AgentSceneObject, AgentStyle
from app.schemas import CommandPlan, OperationRequest


def test_build_command_plan_uses_agent_for_unclear_complex_command(monkeypatch) -> None:
    from app import main

    async def fake_plan_with_drawing_agent(text: str, *, rule_plan: CommandPlan | None = None) -> CommandPlan:
        return CommandPlan(
            raw_text=text,
            normalized_text=text,
            operations=[
                OperationRequest(
                    operation_type="add_object",
                    payload={
                        "object": {
                            "type": "circle",
                            "name": "太阳",
                            "geometry": {"cx": 512, "cy": 160, "radius": 70},
                            "style": {"fill": "#facc15", "stroke": "#facc15", "strokeWidth": 2, "opacity": 1},
                        }
                    },
                )
            ],
            confidence=0.8,
            planner_source="agent",
        )

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_drawing_agent", fake_plan_with_drawing_agent)

    plan = asyncio.run(main.build_command_plan("画一个森林场景然后加一些层次"))

    assert plan.operations[0].payload["object"]["name"] == "太阳"
    assert plan.planner_source == "agent"
    assert plan.explanation == "准备执行 1 个绘图步骤"


def test_build_command_plan_falls_back_when_agent_fails(monkeypatch) -> None:
    from app import main

    async def fake_plan_with_drawing_agent(_: str, *, rule_plan: CommandPlan | None = None) -> CommandPlan:
        raise DrawingAgentError("network failed")

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_drawing_agent", fake_plan_with_drawing_agent)

    plan = asyncio.run(main.build_command_plan("画一个森林场景然后加一些层次"))

    assert plan.requires_confirmation is True
    assert plan.operations == []
    assert plan.planner_source == "rules_fallback"
    assert plan.explanation is not None


def test_build_command_plan_skips_mimo_for_voice_noise(monkeypatch) -> None:
    from app import main

    called = False

    async def fake_plan_with_drawing_agent(_: str, *, rule_plan: CommandPlan | None = None) -> CommandPlan:
        nonlocal called
        called = True
        raise AssertionError("voice noise should not call MiMo")

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_drawing_agent", fake_plan_with_drawing_agent)

    result = asyncio.run(main.build_command_plan_with_metrics("然后。"))

    assert called is False
    assert result.plan.requires_confirmation is True
    assert result.plan.operations == []
    assert result.plan.planner_source == "rules"
    assert result.metrics.llm_attempted is False
    assert result.metrics.planner_source == "rules"


def test_build_command_plan_metrics_track_rule_parser(monkeypatch) -> None:
    from app import main

    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("AI_PAINTING_ENABLE_LLM_PLANNER", "false")

    result = asyncio.run(main.build_command_plan_with_metrics("画一个蓝色圆形"))

    assert result.plan.planner_source == "rules"
    assert result.metrics.planner_source == "rules"
    assert result.metrics.rule_parse_ms is not None
    assert result.metrics.planner_total_ms is not None
    assert result.metrics.llm_attempted is False


def test_agent_template_builds_complex_living_room(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个温馨客厅，有沙发、茶几、窗户和落地灯"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.expected_object_count == 14
    assert len(result.plan.operations) == 14
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "sofa" in semantic_tags
    assert "coffee_table" in semantic_tags
    assert "floor_lamp" in semantic_tags
    assert result.metrics.llm_attempted is True
    assert result.metrics.llm_succeeded is True
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True
    assert result.metrics.agent_planner_ms is not None


def test_agent_template_builds_voice_flowchart(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个语音绘图流程图，从用户语音到ASR，再到规划器，最后到画布执行"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "diagram_scene"
    assert result.plan.scene_plan.expected_object_count == 12
    assert len(result.plan.operations) == 12
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 4
    assert object_types.count("text") == 5
    assert object_types.count("arrow") == 3
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "diagram.node" in semantic_tags
    assert "diagram.connector" in semantic_tags
    assert "flowchart" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_builds_infographic(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个销售增长信息图，包含营收、转化率、复购率和三个月柱状图"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "infographic_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 7
    assert object_types.count("text") == 11
    assert object_types.count("line") == 2
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "infographic.metric_card" in semantic_tags
    assert "infographic.bar" in semantic_tags
    assert "bar_chart" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_model_scene_graph_runs_through_graph(monkeypatch) -> None:
    from app import main
    from app.agent import planner

    async def fake_build_scene_graph(text: str) -> AgentSceneGraph:
        return AgentSceneGraph(
            intent="compose_scene",
            domain="office_scene",
            summary=f"绘制{text}",
            objects=[
                AgentSceneObject(
                    object_id="office-window",
                    type="rect",
                    name="办公室窗户",
                    layer_id="foreground",
                    group_id="office",
                    semantic_tags=["window"],
                    geometry={"x": 650, "y": 130, "width": 180, "height": 130, "radius": 8},
                    style=AgentStyle(fill="#bfdbfe", stroke="#1e3a8a", strokeWidth=3, opacity=1),
                )
            ],
            relations=[],
            confidence=0.8,
        )

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(planner, "build_scene_graph_with_mimo", fake_build_scene_graph)
    monkeypatch.setattr(planner, "repair_scene_graph_with_mimo", None)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个办公室场景然后加一个窗户"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "office_scene"
    assert result.plan.operations[0].payload["object"]["name"] == "办公室窗户"
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True
    assert result.metrics.agent_planner_ms == result.metrics.llm_planner_ms
