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


def test_agent_edit_planner_builds_semantic_multi_step_edit(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("把客厅的沙发改成绿色并向右移动一点"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.intent == "edit_scene"
    assert [operation.operation_type for operation in result.plan.operations] == ["set_style_many", "move_many"]
    assert result.plan.operations[0].payload["target"] == {"selector": "all", "semantic_tag": "sofa"}
    assert result.plan.operations[0].payload["style"] == {"fill": "#16a34a", "stroke": "#16a34a"}
    assert result.plan.operations[1].payload["target"] == {"selector": "all", "semantic_tag": "sofa"}
    assert result.plan.operations[1].payload["dx"] == 20
    assert result.plan.operations[1].payload["dy"] == 0
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_edit_planner_supports_different_targets_per_clause(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("把流程图节点改成浅蓝色，同时把箭头加粗"))

    assert result.plan.planner_source == "agent"
    assert [operation.operation_type for operation in result.plan.operations] == ["set_style_many", "set_style_many"]
    assert result.plan.operations[0].payload["target"] == {"selector": "all", "semantic_tag": "diagram.node"}
    assert result.plan.operations[0].payload["style"] == {"fill": "#7dd3fc", "stroke": "#7dd3fc"}
    assert result.plan.operations[1].payload["target"] == {"selector": "all", "semantic_tag": "diagram.connector"}
    assert result.plan.operations[1].payload["style"] == {"strokeWidth": 5}


def test_agent_edit_planner_builds_object_query_dsl_targets(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    ranked_result = asyncio.run(main.build_command_plan_with_metrics("把左边第二棵树改成黄色"))
    ranked_target = ranked_result.plan.operations[0].payload["target"]

    assert ranked_result.plan.planner_source == "agent"
    assert ranked_result.plan.operations[0].operation_type == "set_style_many"
    assert ranked_target["semantic_tag"] == "tree"
    assert ranked_target["position"] == "leftmost"
    assert ranked_target["position_rank"] == 2
    assert ranked_target["include_group_members"] is True

    relative_result = asyncio.run(main.build_command_plan_with_metrics("把屋顶下面的门改成绿色"))
    relative_target = relative_result.plan.operations[0].payload["target"]

    assert relative_result.plan.planner_source == "agent"
    assert relative_target["semantic_tag"] == "house.door"
    assert relative_target["relative_to"] == {"relation": "below", "target": {"selector": "all", "semantic_tag": "house.roof"}}

    near_tree_result = asyncio.run(main.build_command_plan_with_metrics("把靠近门的那棵树改成黄色"))
    near_tree_target = near_tree_result.plan.operations[0].payload["target"]

    assert near_tree_result.plan.planner_source == "agent"
    assert near_tree_result.plan.operations[0].operation_type == "set_style_many"
    assert near_tree_target["semantic_tag"] == "tree"
    assert near_tree_target["include_group_members"] is True
    assert near_tree_target["relative_to"] == {
        "relation": "near",
        "max_distance": 260,
        "target": {"selector": "all", "semantic_tag": "house.door"},
    }

    covering_image_result = asyncio.run(main.build_command_plan_with_metrics("把挡住标题的图片向右移动一点"))
    covering_image_target = covering_image_result.plan.operations[0].payload["target"]

    assert covering_image_result.plan.planner_source == "agent"
    assert covering_image_result.plan.operations[0].operation_type == "move_many"
    assert covering_image_target["type"] == "image"
    assert covering_image_target["relative_to"] == {
        "relation": "covering",
        "target": {"selector": "all", "semantic_tag": "poster.headline"},
    }

    inside_text_result = asyncio.run(main.build_command_plan_with_metrics("把卡片里的文字改成蓝色"))
    inside_text_target = inside_text_result.plan.operations[0].payload["target"]

    assert inside_text_result.plan.planner_source == "agent"
    assert inside_text_result.plan.operations[0].operation_type == "set_style_many"
    assert inside_text_target["type"] == "text"
    assert inside_text_target["relative_to"] == {
        "relation": "inside",
        "margin": 8,
        "target": {
            "selector": "all",
            "semantic_tags": ["poster.hero", "ui.hero", "ui.metric", "ui.chart", "infographic.metric_card", "org_chart.node"],
        },
    }

    same_row_button_result = asyncio.run(main.build_command_plan_with_metrics("把和标题同一行的按钮改成绿色"))
    same_row_button_target = same_row_button_result.plan.operations[0].payload["target"]

    assert same_row_button_result.plan.planner_source == "agent"
    assert same_row_button_result.plan.operations[0].operation_type == "set_style_many"
    assert same_row_button_target["semantic_tags"] == ["poster.cta", "ui.cta"]
    assert same_row_button_target["relative_to"] == {
        "relation": "same_row",
        "tolerance": 48,
        "target": {"selector": "all", "semantic_tag": "poster.headline"},
    }

    chained_relation_result = asyncio.run(main.build_command_plan_with_metrics("把卡片里和标题同一行的按钮改成绿色"))
    chained_relation_target = chained_relation_result.plan.operations[0].payload["target"]

    assert chained_relation_result.plan.planner_source == "agent"
    assert chained_relation_result.plan.operations[0].operation_type == "set_style_many"
    assert chained_relation_target["semantic_tags"] == ["poster.cta", "ui.cta"]
    assert chained_relation_target["relative_to_all"] == [
        {
            "relation": "inside",
            "margin": 8,
            "target": {
                "selector": "all",
                "semantic_tags": ["poster.hero", "ui.hero", "ui.metric", "ui.chart", "infographic.metric_card", "org_chart.node"],
            },
        },
        {"relation": "same_row", "tolerance": 48, "target": {"selector": "all", "semantic_tag": "poster.headline"}},
    ]

    front_image_result = asyncio.run(main.build_command_plan_with_metrics("把标题上层的图片向右移动一点"))
    front_image_target = front_image_result.plan.operations[0].payload["target"]

    assert front_image_result.plan.planner_source == "agent"
    assert front_image_result.plan.operations[0].operation_type == "move_many"
    assert front_image_target["type"] == "image"
    assert front_image_target["relative_to"] == {
        "relation": "front_of",
        "target": {"selector": "all", "semantic_tag": "poster.headline"},
    }

    color_group_result = asyncio.run(main.build_command_plan_with_metrics("把所有暖色小物件向上移动一点"))
    color_group_target = color_group_result.plan.operations[0].payload["target"]

    assert color_group_result.plan.planner_source == "agent"
    assert color_group_result.plan.operations[0].operation_type == "move_many"
    assert color_group_target["color_group"] == "warm"
    assert color_group_target["size_class"] == "small"
    assert color_group_target["max_area"] == 25000

    group_result = asyncio.run(main.build_command_plan_with_metrics("把整个沙发向右移动一点"))
    group_target = group_result.plan.operations[0].payload["target"]

    assert group_result.plan.planner_source == "agent"
    assert group_result.plan.operations[0].operation_type == "move_many"
    assert group_target["semantic_tag"] == "sofa"
    assert group_target["include_group_members"] is True


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


def test_agent_template_builds_launch_poster(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个AI语音绘图新品发布海报，突出主标题、产品视觉、三个卖点和立即体验按钮"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "poster_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 6
    assert object_types.count("text") == 8
    assert object_types.count("circle") == 4
    assert object_types.count("ellipse") == 1
    assert object_types.count("path") == 1
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "poster.headline" in semantic_tags
    assert "poster.hero" in semantic_tags
    assert "poster.cta" in semantic_tags
    assert "poster.feature_text" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_does_not_override_generative_art_request(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")

    result = asyncio.run(main.build_command_plan_with_metrics("画一个复杂艺术海报，国风水墨质感"))

    assert result.plan.planner_source == "rules"
    assert result.plan.operations[0].operation_type == "generate_image_asset"
    assert result.metrics.agent_attempted is False
    assert result.metrics.llm_attempted is False


def test_agent_template_builds_ui_wireframe(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个语音绘图产品的UI草图，包含侧边导航、顶部栏、搜索框、主卡片、趋势图和新建作品按钮"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "ui_wireframe_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 13
    assert object_types.count("text") == 6
    assert object_types.count("circle") == 1
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "ui.sidebar" in semantic_tags
    assert "ui.search" in semantic_tags
    assert "ui.hero" in semantic_tags
    assert "ui.cta" in semantic_tags
    assert "ui_wireframe" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_builds_system_architecture_diagram(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(
        main.build_command_plan_with_metrics("画一个AI绘图系统架构图，包含前端、后端、ASR服务、Agent规划器、SQLite数据库和图像生成服务")
    )

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "system_architecture_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 7
    assert object_types.count("text") == 8
    assert object_types.count("line") == 5
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "system_architecture.client" in semantic_tags
    assert "system_architecture.backend" in semantic_tags
    assert "system_architecture.asr" in semantic_tags
    assert "system_architecture.agent" in semantic_tags
    assert "system_architecture.database" in semantic_tags
    assert "system_architecture.image_provider" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_builds_er_diagram(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个用户订单ER图，包含用户、订单、商品和支付"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "er_diagram_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 5
    assert object_types.count("text") == 12
    assert object_types.count("line") == 3
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "er_diagram.entity" in semantic_tags
    assert "er_diagram.attribute" in semantic_tags
    assert "er_diagram.relationship" in semantic_tags
    assert "er_diagram.entity.user" in semantic_tags
    assert "er_diagram.entity.order" in semantic_tags
    assert "er_diagram.entity.product" in semantic_tags
    assert "er_diagram.entity.payment" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_builds_org_chart(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个产品团队组织结构图，包括负责人、产品组、设计组、研发组和执行角色"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "org_chart_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 8
    assert object_types.count("text") == 9
    assert object_types.count("line") == 3
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "org_chart.node" in semantic_tags
    assert "org_chart.connector" in semantic_tags
    assert "org_chart.department" in semantic_tags
    assert "org_chart.role" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_extracts_custom_org_chart_names(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(
        main.build_command_plan_with_metrics(
            "画一个产品团队组织结构图，包括负责人、产品经理、设计负责人、研发负责人、用户研究员、交互设计师、前端工程师、后端工程师"
        )
    )

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "org_chart_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    objects = [operation.payload["object"] for operation in result.plan.operations]
    labels = [
        obj["geometry"]["content"]
        for obj in objects
        if obj["type"] == "text"
        and (
            "org_chart.lead" in obj["semantic_tags"]
            or "org_chart.department" in obj["semantic_tags"]
            or "org_chart.role" in obj["semantic_tags"]
        )
    ]
    assert labels == [
        "负责人",
        "产品经理",
        "设计负责人",
        "研发负责人",
        "用户研究员",
        "交互设计师",
        "前端工程师",
        "后端工程师",
    ]
    assert "产品经理" in result.plan.explanation
    assert "后端工程师" in result.plan.explanation


def test_agent_template_builds_gantt_chart(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个产品迭代项目排期甘特图，包含需求、设计、开发、测试和上线里程碑"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "gantt_chart_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 6
    assert object_types.count("text") == 11
    assert object_types.count("line") == 2
    assert object_types.count("circle") == 1
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "gantt_chart.timeline" in semantic_tags
    assert "gantt_chart.task_bar" in semantic_tags
    assert "gantt_chart.milestone" in semantic_tags
    assert "gantt_chart.legend" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_builds_swimlane_diagram(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个泳道图，包含销售、运营和交付"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "swimlane_diagram_scene"
    assert result.plan.scene_plan.expected_object_count == 18
    assert len(result.plan.operations) == 18
    object_types = [operation.payload["object"]["type"] for operation in result.plan.operations]
    assert object_types.count("rect") == 7
    assert object_types.count("text") == 7
    assert object_types.count("line") == 4
    semantic_tags = [tag for operation in result.plan.operations for tag in operation.payload["object"]["semantic_tags"]]
    assert "swimlane_diagram.lane" in semantic_tags
    assert "swimlane_diagram.lane_label" in semantic_tags
    assert "swimlane_diagram.step" in semantic_tags
    assert "swimlane_diagram.connector" in semantic_tags
    assert result.metrics.agent_attempted is True
    assert result.metrics.agent_succeeded is True


def test_agent_template_extracts_custom_swimlane_names(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(main.build_command_plan_with_metrics("画一个泳道图，泳道包括产品、设计、研发、测试"))

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "swimlane_diagram_scene"
    assert result.plan.scene_plan.expected_object_count == 20
    assert len(result.plan.operations) == 20

    objects = [operation.payload["object"] for operation in result.plan.operations]
    lane_labels = [
        obj["geometry"]["content"]
        for obj in objects
        if "swimlane_diagram.lane_label" in obj["semantic_tags"]
    ]
    assert lane_labels == ["产品", "设计", "研发", "测试"]

    object_types = [obj["type"] for obj in objects]
    assert object_types.count("rect") == 8
    assert object_types.count("text") == 8
    assert object_types.count("line") == 4


def test_agent_template_extracts_custom_swimlane_step_names(monkeypatch) -> None:
    from app import main

    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    result = asyncio.run(
        main.build_command_plan_with_metrics("画一个泳道图，泳道包括产品、设计、研发、测试，节点包括需求评审、原型设计、开发联调、验收发布")
    )

    assert result.plan.planner_source == "agent"
    assert result.plan.scene_plan is not None
    assert result.plan.scene_plan.steps[0].target["domain"] == "swimlane_diagram_scene"
    assert result.plan.scene_plan.expected_object_count == 20

    objects = [operation.payload["object"] for operation in result.plan.operations]
    step_labels = [
        obj["geometry"]["content"]
        for obj in objects
        if "swimlane_diagram.step_label" in obj["semantic_tags"]
    ]
    assert step_labels == ["需求评审", "原型设计", "开发联调", "验收发布"]
    assert "需求评审" in result.plan.explanation
    assert "验收发布" in result.plan.explanation


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
