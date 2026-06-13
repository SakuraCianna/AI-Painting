from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from ..command_parser import is_voice_noise_input, normalize_text
from ..schemas import CommandPlan
from .compiler import ALLOWED_OBJECT_TYPES, ALLOWED_OPERATION_TYPES
from .graph import run_drawing_agent_graph
from .model_client import AgentModelError, build_scene_graph_with_mimo, has_mimo_model_config, repair_scene_graph_with_mimo
from .scene_graph import AgentSceneGraph, AgentSceneObject, AgentSceneRelation, AgentStyle
from .validator import SceneGraphValidationError


COMPLEX_HINTS = ("然后", "并且", "同时", "接着", "再", "之后", "最后", "一排", "围绕", "组合", "场景")
AGENT_SCENE_HINTS = ("客厅", "卧室", "厨房", "办公室", "教室", "城市", "花园", "海报", "信息图", "流程图", "结构图")


class DrawingAgentError(RuntimeError):
    pass


def is_drawing_agent_enabled() -> bool:
    value = os.getenv("AI_PAINTING_ENABLE_AGENT_PLANNER")
    if value is None:
        value = os.getenv("AI_PAINTING_ENABLE_LLM_PLANNER", "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_use_drawing_agent(text: str, rule_plan: CommandPlan) -> bool:
    if is_voice_noise_input(text):
        return False
    if not is_drawing_agent_enabled():
        return False
    normalized = normalize_text(text)
    if _local_scene_graph_for_text(normalized) is not None:
        return True
    if not has_mimo_model_config():
        return False
    if rule_plan.requires_confirmation and rule_plan.confidence <= 0.45:
        return True
    if any(hint in normalized for hint in COMPLEX_HINTS + AGENT_SCENE_HINTS) and len(rule_plan.operations) <= 1:
        return True
    return False


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _validate_command_plan(plan: CommandPlan) -> CommandPlan:
    if len(plan.operations) > _read_int_env("AI_PAINTING_AGENT_MAX_OPERATIONS", 20):
        raise DrawingAgentError("Drawing Agent 规划步骤过多")
    for operation in plan.operations:
        if operation.operation_type not in ALLOWED_OPERATION_TYPES:
            raise DrawingAgentError(f"Drawing Agent 包含不支持的操作: {operation.operation_type}")
        obj = operation.payload.get("object")
        if isinstance(obj, dict) and obj.get("type") not in ALLOWED_OBJECT_TYPES:
            raise DrawingAgentError(f"Drawing Agent 包含不支持的对象: {obj.get('type')}")
    if not plan.operations and not plan.requires_confirmation:
        raise DrawingAgentError("Drawing Agent 没有可执行操作")
    plan.confidence = min(plan.confidence, 0.84)
    plan.planner_source = "agent"
    return plan


def _style(fill: str, stroke: str = "#111827", stroke_width: float = 2, opacity: float = 1) -> AgentStyle:
    return AgentStyle(fill=fill, stroke=stroke, strokeWidth=stroke_width, opacity=opacity)


def _object(
    object_id: str,
    object_type: str,
    name: str,
    geometry: dict[str, Any],
    fill: str,
    *,
    stroke: str = "#111827",
    stroke_width: float = 2,
    layer_id: str = "middle",
    group_id: str | None = None,
    semantic_tags: list[str] | None = None,
    z_index: int = 0,
    role: str | None = None,
) -> AgentSceneObject:
    return AgentSceneObject(
        object_id=object_id,
        type=object_type,  # type: ignore[arg-type]
        name=name,
        layer_id=layer_id,
        group_id=group_id,
        semantic_tags=semantic_tags or [],
        geometry=geometry,
        style=_style(fill, stroke, stroke_width),
        z_index=z_index,
        role=role,
    )


def _living_room_scene_graph(text: str) -> AgentSceneGraph:
    warm = "温馨" in text or "暖" in text
    wall_color = "#f8fafc" if not warm else "#fff7ed"
    sofa_color = "#2563eb" if "蓝" in text else "#0b57d0"
    lamp_color = "#facc15" if warm else "#fde68a"
    objects = [
        _object("wall", "rect", "客厅墙面", {"x": 0, "y": 0, "width": 1024, "height": 430}, wall_color, stroke=wall_color, layer_id="background", semantic_tags=["room.wall", "living_room"]),
        _object("floor", "rect", "木地板", {"x": 0, "y": 430, "width": 1024, "height": 338}, "#e7e5e4", stroke="#d6d3d1", layer_id="background", semantic_tags=["room.floor", "living_room"]),
        _object("rug", "ellipse", "圆角地毯", {"cx": 430, "cy": 635, "rx": 250, "ry": 72}, "#dbeafe", stroke="#93c5fd", stroke_width=3, group_id="living-room", semantic_tags=["rug", "living_room"], z_index=1),
        _object("sofa-back", "rect", "沙发靠背", {"x": 245, "y": 345, "width": 350, "height": 120, "radius": 28}, sofa_color, stroke="#041e49", stroke_width=3, group_id="sofa", semantic_tags=["sofa", "living_room"], z_index=2),
        _object("sofa-seat", "rect", "沙发坐垫", {"x": 220, "y": 430, "width": 400, "height": 115, "radius": 24}, "#3b82f6", stroke="#041e49", stroke_width=3, group_id="sofa", semantic_tags=["sofa", "sofa.seat", "living_room"], z_index=3),
        _object("sofa-left-arm", "rect", "左扶手", {"x": 200, "y": 405, "width": 60, "height": 135, "radius": 18}, "#1d4ed8", stroke="#041e49", stroke_width=3, group_id="sofa", semantic_tags=["sofa.arm", "living_room"], z_index=4),
        _object("sofa-right-arm", "rect", "右扶手", {"x": 580, "y": 405, "width": 60, "height": 135, "radius": 18}, "#1d4ed8", stroke="#041e49", stroke_width=3, group_id="sofa", semantic_tags=["sofa.arm", "living_room"], z_index=4),
        _object("coffee-table", "ellipse", "椭圆茶几", {"cx": 430, "cy": 580, "rx": 135, "ry": 38}, "#92400e", stroke="#451a03", stroke_width=3, group_id="living-room", semantic_tags=["coffee_table", "living_room"], z_index=5),
        _object("window", "rect", "窗户", {"x": 710, "y": 120, "width": 190, "height": 150, "radius": 8}, "#bfdbfe", stroke="#1e3a8a", stroke_width=4, group_id="window", semantic_tags=["window", "living_room"], z_index=2),
        _object("window-vertical", "line", "窗户竖框", {"x1": 805, "y1": 120, "x2": 805, "y2": 270}, "transparent", stroke="#1e3a8a", stroke_width=3, group_id="window", semantic_tags=["window.frame", "living_room"], z_index=3),
        _object("window-horizontal", "line", "窗户横框", {"x1": 710, "y1": 195, "x2": 900, "y2": 195}, "transparent", stroke="#1e3a8a", stroke_width=3, group_id="window", semantic_tags=["window.frame", "living_room"], z_index=3),
        _object("lamp-stand", "line", "落地灯支架", {"x1": 155, "y1": 315, "x2": 155, "y2": 555}, "transparent", stroke="#374151", stroke_width=5, group_id="floor-lamp", semantic_tags=["floor_lamp", "living_room"], z_index=4),
        _object("lamp-shade", "triangle", "落地灯灯罩", {"x": 155, "y": 315, "size": 105}, lamp_color, stroke="#92400e", stroke_width=3, group_id="floor-lamp", semantic_tags=["floor_lamp", "lamp.shade", "living_room"], z_index=5),
        _object("lamp-base", "ellipse", "落地灯底座", {"cx": 155, "cy": 560, "rx": 48, "ry": 14}, "#6b7280", stroke="#374151", stroke_width=2, group_id="floor-lamp", semantic_tags=["floor_lamp", "lamp.base", "living_room"], z_index=5),
    ]
    relations = [
        AgentSceneRelation(subject="sofa-seat", relation="in_front_of", target="wall", note="沙发位于墙面前方"),
        AgentSceneRelation(subject="coffee-table", relation="in_front_of", target="sofa-seat", note="茶几在沙发前方"),
        AgentSceneRelation(subject="floor-lamp", relation="left_of", target="sofa-seat", note="落地灯在沙发左侧"),
        AgentSceneRelation(subject="window", relation="right_of", target="sofa-seat", note="窗户在画面右侧"),
    ]
    return AgentSceneGraph(
        intent="compose_scene",
        domain="interior_vector_scene",
        summary="绘制包含沙发、茶几、窗户、地毯和落地灯的客厅场景",
        background=wall_color,
        objects=objects,
        relations=relations,
        confidence=0.83,
    )


def _flowchart_scene_graph(text: str) -> AgentSceneGraph:
    if any(keyword in text for keyword in ("架构", "结构图", "系统")):
        labels = ["语音输入", "ASR服务", "意图分类", "任务规划", "绘图执行"]
        summary = "绘制语音绘图系统结构图"
    else:
        labels = ["用户语音", "ASR识别", "Agent规划", "画布执行"]
        summary = "绘制从语音输入到画布执行的流程图"

    node_width = 138 if len(labels) >= 5 else 160
    node_height = 92
    gap = 36 if len(labels) >= 5 else 72
    total_width = (node_width * len(labels)) + (gap * (len(labels) - 1))
    start_x = (1024 - total_width) / 2
    node_y = 338
    objects = [
        _object(
            "diagram-title",
            "text",
            "流程图标题",
            {"x": 512, "y": 190, "content": "语音绘图流程", "fontSize": 34},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="voice-flowchart",
            semantic_tags=["diagram.title", "flowchart"],
            z_index=20,
        )
    ]
    relations: list[AgentSceneRelation] = []

    for index, label in enumerate(labels):
        x = round(start_x + index * (node_width + gap), 2)
        node_id = f"flow-node-{index + 1}"
        text_id = f"flow-label-{index + 1}"
        fill = "#e8f0fe" if index in {0, len(labels) - 1} else "#f1f3f4"
        stroke = "#1a73e8" if index in {0, len(labels) - 1} else "#5f6368"
        objects.append(
            _object(
                node_id,
                "rect",
                label,
                {"x": x, "y": node_y, "width": node_width, "height": node_height, "radius": 18},
                fill,
                stroke=stroke,
                stroke_width=3,
                layer_id="middle",
                group_id="voice-flowchart",
                semantic_tags=["diagram.node", "flowchart", f"flowchart.step.{index + 1}"],
                z_index=index * 3,
                role="process_node",
            )
        )
        objects.append(
            _object(
                text_id,
                "text",
                f"{label}标签",
                {"x": round(x + node_width / 2, 2), "y": node_y + node_height / 2, "content": label, "fontSize": 24},
                "#202124",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="voice-flowchart",
                semantic_tags=["diagram.label", "flowchart", f"flowchart.step.{index + 1}"],
                z_index=(index * 3) + 1,
                role="label",
            )
        )

        if index > 0:
            previous_node_id = f"flow-node-{index}"
            arrow_id = f"flow-arrow-{index}"
            previous_x = round(start_x + (index - 1) * (node_width + gap), 2)
            objects.append(
                _object(
                    arrow_id,
                    "arrow",
                    f"{labels[index - 1]}到{label}",
                    {
                        "x1": round(previous_x + node_width + 8, 2),
                        "y1": node_y + node_height / 2,
                        "x2": round(x - 8, 2),
                        "y2": node_y + node_height / 2,
                    },
                    "transparent",
                    stroke="#5f6368",
                    stroke_width=4,
                    layer_id="middle",
                    group_id="voice-flowchart",
                    semantic_tags=["diagram.connector", "flowchart"],
                    z_index=(index * 3) - 1,
                    role="connector",
                )
            )
            relations.append(
                AgentSceneRelation(
                    subject=previous_node_id,
                    relation="flows_to",
                    target=node_id,
                    note=f"{labels[index - 1]}流向{label}",
                )
            )

    return AgentSceneGraph(
        intent="compose_diagram",
        domain="diagram_scene",
        summary=summary,
        background="#ffffff",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _infographic_scene_graph(text: str) -> AgentSceneGraph:
    if "销售" in text or "营收" in text:
        title = "销售增长信息图"
        metrics = [
            ("营收", "128万", "#e8f0fe"),
            ("转化率", "18%", "#e6f4ea"),
            ("复购率", "42%", "#fef7e0"),
        ]
        bars = [("一月", 120), ("二月", 168), ("三月", 220)]
        summary = "绘制销售增长信息图, 包含关键指标卡片和柱状图"
    else:
        title = "项目进展信息图"
        metrics = [
            ("完成度", "76%", "#e8f0fe"),
            ("任务数", "24", "#e6f4ea"),
            ("风险项", "3", "#fce8e6"),
        ]
        bars = [("设计", 170), ("开发", 225), ("测试", 145)]
        summary = "绘制项目进展信息图, 包含指标卡片和阶段柱状图"

    objects = [
        _object(
            "infographic-title",
            "text",
            "信息图标题",
            {"x": 512, "y": 92, "content": title, "fontSize": 38},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="infographic",
            semantic_tags=["infographic.title", "infographic"],
            z_index=30,
        ),
        _object(
            "infographic-subtitle",
            "text",
            "信息图副标题",
            {"x": 512, "y": 142, "content": "语音生成的可编辑数据版式", "fontSize": 20},
            "#5f6368",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="infographic",
            semantic_tags=["infographic.subtitle", "infographic"],
            z_index=31,
        ),
    ]

    card_width = 240
    card_height = 120
    for index, (label, value, fill) in enumerate(metrics):
        x = 112 + index * 280
        objects.extend(
            [
                _object(
                    f"metric-card-{index + 1}",
                    "rect",
                    f"{label}指标卡",
                    {"x": x, "y": 205, "width": card_width, "height": card_height, "radius": 22},
                    fill,
                    stroke="#dadce0",
                    stroke_width=2,
                    layer_id="middle",
                    group_id="infographic",
                    semantic_tags=["infographic.metric_card", "infographic", f"metric.{index + 1}"],
                    z_index=index * 3,
                    role="metric_card",
                ),
                _object(
                    f"metric-value-{index + 1}",
                    "text",
                    f"{label}数值",
                    {"x": x + card_width / 2, "y": 252, "content": value, "fontSize": 34},
                    "#202124",
                    stroke="transparent",
                    stroke_width=0,
                    layer_id="foreground",
                    group_id="infographic",
                    semantic_tags=["infographic.metric_value", "infographic", f"metric.{index + 1}"],
                    z_index=(index * 3) + 1,
                    role="metric_value",
                ),
                _object(
                    f"metric-label-{index + 1}",
                    "text",
                    f"{label}标签",
                    {"x": x + card_width / 2, "y": 292, "content": label, "fontSize": 20},
                    "#5f6368",
                    stroke="transparent",
                    stroke_width=0,
                    layer_id="foreground",
                    group_id="infographic",
                    semantic_tags=["infographic.metric_label", "infographic", f"metric.{index + 1}"],
                    z_index=(index * 3) + 2,
                    role="metric_label",
                ),
            ]
        )

    objects.extend(
        [
            _object(
                "chart-panel",
                "rect",
                "柱状图区",
                {"x": 120, "y": 390, "width": 784, "height": 255, "radius": 24},
                "#ffffff",
                stroke="#dadce0",
                stroke_width=2,
                layer_id="middle",
                group_id="infographic",
                semantic_tags=["infographic.chart_panel", "infographic", "bar_chart"],
                z_index=12,
                role="chart_panel",
            ),
            _object(
                "chart-y-axis",
                "line",
                "柱状图纵轴",
                {"x1": 205, "y1": 590, "x2": 205, "y2": 430},
                "transparent",
                stroke="#5f6368",
                stroke_width=3,
                layer_id="foreground",
                group_id="infographic",
                semantic_tags=["infographic.axis", "bar_chart"],
                z_index=13,
            ),
            _object(
                "chart-x-axis",
                "line",
                "柱状图横轴",
                {"x1": 205, "y1": 590, "x2": 820, "y2": 590},
                "transparent",
                stroke="#5f6368",
                stroke_width=3,
                layer_id="foreground",
                group_id="infographic",
                semantic_tags=["infographic.axis", "bar_chart"],
                z_index=14,
            ),
        ]
    )

    for index, (label, height) in enumerate(bars):
        x = 305 + index * 165
        bar_y = 590 - height
        objects.append(
            _object(
                f"bar-{index + 1}",
                "rect",
                f"{label}柱形",
                {"x": x, "y": bar_y, "width": 78, "height": height, "radius": 14},
                ["#1a73e8", "#34a853", "#fbbc04"][index],
                stroke="transparent",
                stroke_width=0,
                layer_id="middle",
                group_id="infographic",
                semantic_tags=["infographic.bar", "bar_chart", f"bar.{index + 1}"],
                z_index=15 + index,
                role="bar",
            )
        )
        objects.append(
            _object(
                f"bar-label-{index + 1}",
                "text",
                f"{label}标签",
                {"x": x + 39, "y": 622, "content": label, "fontSize": 19},
                "#5f6368",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="infographic",
                semantic_tags=["infographic.bar_label", "bar_chart", f"bar.{index + 1}"],
                z_index=20 + index,
                role="bar_label",
            )
        )

    relations = [
        AgentSceneRelation(subject="metric-card-1", relation="supports", target="chart-panel", note="指标卡解释图表趋势"),
        AgentSceneRelation(subject="metric-card-2", relation="supports", target="chart-panel", note="指标卡解释图表趋势"),
        AgentSceneRelation(subject="metric-card-3", relation="supports", target="chart-panel", note="指标卡解释图表趋势"),
    ]
    return AgentSceneGraph(
        intent="compose_infographic",
        domain="infographic_scene",
        summary=summary,
        background="#f8fafc",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _local_scene_graph_for_text(normalized_text: str) -> AgentSceneGraph | None:
    if "信息图" in normalized_text and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _infographic_scene_graph(normalized_text)
    if any(keyword in normalized_text for keyword in ("流程图", "结构图", "架构图")) and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _flowchart_scene_graph(normalized_text)
    if "客厅" in normalized_text and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _living_room_scene_graph(normalized_text)
    return None


async def plan_with_drawing_agent(text: str, *, rule_plan: CommandPlan | None = None) -> CommandPlan:
    normalized = normalize_text(text)
    try:
        scene_graph = _local_scene_graph_for_text(normalized)
        plan = await run_drawing_agent_graph(
            text,
            normalized,
            scene_graph=scene_graph,
            scene_graph_builder=None if scene_graph is not None else build_scene_graph_with_mimo,
            scene_graph_repairer=repair_scene_graph_with_mimo if has_mimo_model_config() else None,
        )
        return _validate_command_plan(plan)
    except AgentModelError as exc:
        raise DrawingAgentError(str(exc)) from exc
    except (SceneGraphValidationError, ValidationError) as exc:
        raise DrawingAgentError("Drawing Agent 计划校验失败") from exc
