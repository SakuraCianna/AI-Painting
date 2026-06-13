from __future__ import annotations

import os
import re
from typing import Any

from pydantic import ValidationError

from ..command_parser import is_voice_noise_input, normalize_text
from ..schemas import CommandPlan
from .compiler import ALLOWED_OBJECT_TYPES, ALLOWED_OPERATION_TYPES
from .edit_planner import build_local_edit_plan
from .graph import run_drawing_agent_graph
from .model_client import AgentModelError, build_scene_graph_with_mimo, has_mimo_model_config, repair_scene_graph_with_mimo
from .scene_graph import AgentSceneGraph, AgentSceneObject, AgentSceneRelation, AgentStyle
from .validator import SceneGraphValidationError


COMPLEX_HINTS = ("然后", "并且", "同时", "接着", "再", "之后", "最后", "一排", "围绕", "组合", "场景")
AGENT_SCENE_HINTS = (
    "客厅",
    "卧室",
    "厨房",
    "办公室",
    "教室",
    "城市",
    "花园",
    "海报",
    "信息图",
    "流程图",
    "结构图",
    "泳道图",
    "uml",
    "er图",
    "系统架构",
    "甘特图",
    "排期图",
    "项目排期",
    "进度计划",
    "组织结构",
    "团队架构",
    "组织架构",
    "ui",
    "界面",
    "线框图",
    "草图",
    "原型",
)
SWIMLANE_DEFAULT_LANES = ("销售", "运营", "交付")
SWIMLANE_PALETTE = (
    ("#e8f0fe", "#1a73e8", "#d2e3fc"),
    ("#e6f4ea", "#34a853", "#ceead6"),
    ("#fef7e0", "#fbbc04", "#feefc3"),
    ("#fce8e6", "#ea4335", "#fad2cf"),
)
SWIMLANE_STEP_NAMES = {
    "销售": "线索录入",
    "运营": "资源排期",
    "交付": "交付验收",
    "产品": "需求确认",
    "设计": "方案设计",
    "研发": "开发实现",
    "开发": "开发实现",
    "测试": "测试验收",
}


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
    if any(operation.operation_type in {"generate_image_asset", "polish_image_asset"} for operation in rule_plan.operations):
        return False
    normalized = normalize_text(text)
    if build_local_edit_plan(text, normalized) is not None:
        return True
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


def _poster_scene_graph(text: str) -> AgentSceneGraph:
    is_launch = any(keyword in text for keyword in ("发布", "新品", "上线", "首发"))
    brand = "AI Painting" if "ai" in text or "语音" in text else "NOVA Studio"
    headline = "语音绘图正式发布" if is_launch else "创意工具限时活动"
    subtitle = "只用一句话, 生成可编辑设计画面" if "语音" in text or "绘图" in text else "高效完成海报、图表和视觉草图"
    badge_text = "新品发布" if is_launch else "限时优惠"
    cta_text = "立即体验"
    summary = "绘制产品发布海报, 包含品牌、标题、主视觉、卖点和行动按钮"

    objects = [
        _object(
            "poster-background",
            "rect",
            "海报背景",
            {"x": 0, "y": 0, "width": 1024, "height": 768, "radius": 0},
            "#f8fafc",
            stroke="#f8fafc",
            stroke_width=0,
            layer_id="background",
            group_id="launch-poster",
            semantic_tags=["poster.background", "poster"],
            z_index=-10,
        ),
        _object(
            "poster-accent-left",
            "circle",
            "左侧品牌色块",
            {"cx": 82, "cy": 118, "radius": 120},
            "#e8f0fe",
            stroke="transparent",
            stroke_width=0,
            layer_id="background",
            group_id="launch-poster",
            semantic_tags=["poster.decor", "poster"],
            z_index=-8,
        ),
        _object(
            "poster-accent-right",
            "ellipse",
            "右侧视觉氛围",
            {"cx": 872, "cy": 642, "rx": 180, "ry": 108},
            "#e6f4ea",
            stroke="transparent",
            stroke_width=0,
            layer_id="background",
            group_id="launch-poster",
            semantic_tags=["poster.decor", "poster"],
            z_index=-7,
        ),
        _object(
            "poster-brand-mark",
            "rect",
            "品牌标识底",
            {"x": 104, "y": 72, "width": 56, "height": 56, "radius": 16},
            "#1a73e8",
            stroke="#185abc",
            stroke_width=2,
            layer_id="middle",
            group_id="launch-poster",
            semantic_tags=["poster.brand", "poster"],
            z_index=0,
            role="brand_mark",
        ),
        _object(
            "poster-brand-text",
            "text",
            "品牌文字",
            {"x": 250, "y": 102, "content": brand, "fontSize": 28},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.brand", "poster"],
            z_index=1,
            role="brand_name",
        ),
        _object(
            "poster-badge",
            "rect",
            "海报徽标",
            {"x": 104, "y": 172, "width": 132, "height": 44, "radius": 22},
            "#fef7e0",
            stroke="#fbbc04",
            stroke_width=2,
            layer_id="middle",
            group_id="launch-poster",
            semantic_tags=["poster.badge", "poster"],
            z_index=2,
            role="badge",
        ),
        _object(
            "poster-badge-text",
            "text",
            "徽标文字",
            {"x": 170, "y": 196, "content": badge_text, "fontSize": 20},
            "#92400e",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.badge_text", "poster"],
            z_index=3,
            role="badge_label",
        ),
        _object(
            "poster-headline",
            "text",
            "主标题",
            {"x": 330, "y": 292, "content": headline, "fontSize": 54},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.headline", "poster"],
            z_index=4,
            role="headline",
        ),
        _object(
            "poster-subtitle",
            "text",
            "副标题",
            {"x": 330, "y": 352, "content": subtitle, "fontSize": 24},
            "#5f6368",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.subtitle", "poster"],
            z_index=5,
            role="subtitle",
        ),
        _object(
            "poster-device-card",
            "rect",
            "产品主视觉卡片",
            {"x": 635, "y": 190, "width": 260, "height": 330, "radius": 36},
            "#ffffff",
            stroke="#dadce0",
            stroke_width=3,
            layer_id="middle",
            group_id="launch-poster",
            semantic_tags=["poster.hero", "poster"],
            z_index=6,
            role="hero_visual",
        ),
        _object(
            "poster-device-screen",
            "rect",
            "产品屏幕",
            {"x": 668, "y": 238, "width": 194, "height": 200, "radius": 24},
            "#e8f0fe",
            stroke="#1a73e8",
            stroke_width=3,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.hero.screen", "poster"],
            z_index=7,
            role="hero_screen",
        ),
        _object(
            "poster-hero-line",
            "path",
            "屏幕绘图线",
            {"commands": [{"cmd": "M", "x": 700, "y": 365}, {"cmd": "C", "x1": 735, "y1": 298, "x2": 796, "y2": 418, "x": 835, "y": 320}]},
            "transparent",
            stroke="#1a73e8",
            stroke_width=8,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.hero.stroke", "poster"],
            z_index=8,
            role="hero_stroke",
        ),
        _object(
            "poster-cta-button",
            "rect",
            "行动按钮",
            {"x": 104, "y": 500, "width": 196, "height": 64, "radius": 32},
            "#1a73e8",
            stroke="#185abc",
            stroke_width=2,
            layer_id="middle",
            group_id="launch-poster",
            semantic_tags=["poster.cta", "poster"],
            z_index=9,
            role="cta",
        ),
        _object(
            "poster-cta-text",
            "text",
            "行动按钮文字",
            {"x": 202, "y": 535, "content": cta_text, "fontSize": 24},
            "#ffffff",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="launch-poster",
            semantic_tags=["poster.cta_text", "poster"],
            z_index=10,
            role="cta_label",
        ),
    ]

    feature_items = ["自然语言绘图", "对象可继续编辑", "支持图生图精修"]
    for index, item in enumerate(feature_items):
        y = 612 + index * 42
        objects.append(
            _object(
                f"poster-feature-dot-{index + 1}",
                "circle",
                f"卖点{index + 1}圆点",
                {"cx": 120, "cy": y, "radius": 9},
                "#34a853",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="launch-poster",
                semantic_tags=["poster.feature_dot", "poster", f"poster.feature.{index + 1}"],
                z_index=11 + index * 2,
                role="feature_dot",
            )
        )
        objects.append(
            _object(
                f"poster-feature-text-{index + 1}",
                "text",
                f"卖点{index + 1}",
                {"x": 238, "y": y + 2, "content": item, "fontSize": 22},
                "#3c4043",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="launch-poster",
                semantic_tags=["poster.feature_text", "poster", f"poster.feature.{index + 1}"],
                z_index=12 + index * 2,
                role="feature_text",
            )
        )

    relations = [
        AgentSceneRelation(subject="poster-headline", relation="above", target="poster-subtitle", note="主标题位于副标题上方"),
        AgentSceneRelation(subject="poster-device-card", relation="right_of", target="poster-headline", note="产品主视觉在标题右侧"),
        AgentSceneRelation(subject="poster-cta-button", relation="below", target="poster-subtitle", note="行动按钮在副标题下方"),
    ]
    return AgentSceneGraph(
        intent="compose_poster",
        domain="poster_scene",
        summary=summary,
        background="#f8fafc",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _ui_wireframe_scene_graph(text: str) -> AgentSceneGraph:
    is_dashboard = any(keyword in text for keyword in ("仪表盘", "看板", "数据"))
    product_name = "语音绘图工作台" if "语音" in text or "绘图" in text else "产品控制台"
    hero_title = "开始你的语音创作" if "语音" in text or "绘图" in text else "核心工作区"
    hero_subtitle = "说出目标, Agent 会拆解为可编辑画布对象" if "语音" in text else "一屏完成概览、任务和关键指标"
    metric_value = "12 个对象" if "绘图" in text else "86%"
    summary = "绘制产品界面 UI 草图, 包含导航、顶部栏、搜索、主卡片、图表和行动按钮"

    objects = [
        _object(
            "ui-background",
            "rect",
            "界面背景",
            {"x": 0, "y": 0, "width": 1024, "height": 768, "radius": 0},
            "#f8fafc",
            stroke="#f8fafc",
            stroke_width=0,
            layer_id="background",
            group_id="ui-wireframe",
            semantic_tags=["ui.background", "ui_wireframe"],
            z_index=-10,
        ),
        _object(
            "ui-app-shell",
            "rect",
            "应用外框",
            {"x": 88, "y": 70, "width": 848, "height": 628, "radius": 28},
            "#ffffff",
            stroke="#dadce0",
            stroke_width=3,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.shell", "ui_wireframe"],
            z_index=0,
            role="app_shell",
        ),
        _object(
            "ui-sidebar",
            "rect",
            "侧边导航",
            {"x": 112, "y": 104, "width": 180, "height": 560, "radius": 22},
            "#f1f3f4",
            stroke="#e8eaed",
            stroke_width=2,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.sidebar", "ui_wireframe"],
            z_index=1,
            role="sidebar",
        ),
        _object(
            "ui-active-nav",
            "rect",
            "选中导航项",
            {"x": 134, "y": 188, "width": 136, "height": 48, "radius": 24},
            "#e8f0fe",
            stroke="#1a73e8",
            stroke_width=2,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.nav.active", "ui_wireframe"],
            z_index=2,
            role="navigation_item",
        ),
        _object(
            "ui-nav-label",
            "text",
            "导航文字",
            {"x": 202, "y": 214, "content": "工作台", "fontSize": 20},
            "#1a73e8",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.nav.label", "ui_wireframe"],
            z_index=3,
            role="label",
        ),
        _object(
            "ui-topbar",
            "rect",
            "顶部栏",
            {"x": 318, "y": 104, "width": 588, "height": 72, "radius": 20},
            "#ffffff",
            stroke="#e8eaed",
            stroke_width=2,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.topbar", "ui_wireframe"],
            z_index=4,
            role="topbar",
        ),
        _object(
            "ui-logo",
            "circle",
            "应用图标",
            {"cx": 354, "cy": 140, "radius": 16},
            "#1a73e8",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.logo", "ui_wireframe"],
            z_index=5,
            role="logo",
        ),
        _object(
            "ui-product-name",
            "text",
            "产品名称",
            {"x": 458, "y": 142, "content": product_name, "fontSize": 22},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.product_name", "ui_wireframe"],
            z_index=6,
            role="title",
        ),
        _object(
            "ui-search",
            "rect",
            "搜索框",
            {"x": 672, "y": 118, "width": 200, "height": 44, "radius": 22},
            "#f8fafc",
            stroke="#dadce0",
            stroke_width=2,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.search", "ui_wireframe"],
            z_index=7,
            role="search",
        ),
        _object(
            "ui-hero-card",
            "rect",
            "主内容卡片",
            {"x": 318, "y": 206, "width": 360, "height": 180, "radius": 26},
            "#e8f0fe" if is_dashboard else "#e6f4ea",
            stroke="#dadce0",
            stroke_width=2,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.hero", "ui_wireframe"],
            z_index=9,
            role="hero_card",
        ),
        _object(
            "ui-hero-title",
            "text",
            "主卡片标题",
            {"x": 498, "y": 262, "content": hero_title, "fontSize": 28},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.hero.title", "ui_wireframe"],
            z_index=10,
            role="headline",
        ),
        _object(
            "ui-hero-subtitle",
            "text",
            "主卡片说明",
            {"x": 498, "y": 312, "content": hero_subtitle, "fontSize": 18},
            "#5f6368",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.hero.subtitle", "ui_wireframe"],
            z_index=11,
            role="subtitle",
        ),
        _object(
            "ui-metric-card",
            "rect",
            "指标卡片",
            {"x": 708, "y": 206, "width": 198, "height": 180, "radius": 26},
            "#fef7e0",
            stroke="#fbbc04",
            stroke_width=2,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.metric", "ui_wireframe"],
            z_index=12,
            role="metric_card",
        ),
        _object(
            "ui-metric-value",
            "text",
            "指标数值",
            {"x": 807, "y": 295, "content": metric_value, "fontSize": 30},
            "#92400e",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.metric.value", "ui_wireframe"],
            z_index=13,
            role="metric_value",
        ),
        _object(
            "ui-chart-card",
            "rect",
            "趋势图卡片",
            {"x": 318, "y": 420, "width": 360, "height": 214, "radius": 26},
            "#ffffff",
            stroke="#dadce0",
            stroke_width=2,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.chart", "ui_wireframe"],
            z_index=14,
            role="chart_card",
        ),
        _object(
            "ui-chart-bar-one",
            "rect",
            "趋势柱一",
            {"x": 380, "y": 548, "width": 48, "height": 62, "radius": 12},
            "#1a73e8",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.chart.bar", "ui_wireframe"],
            z_index=15,
            role="chart_bar",
        ),
        _object(
            "ui-chart-bar-two",
            "rect",
            "趋势柱二",
            {"x": 474, "y": 504, "width": 48, "height": 106, "radius": 12},
            "#34a853",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.chart.bar", "ui_wireframe"],
            z_index=16,
            role="chart_bar",
        ),
        _object(
            "ui-chart-bar-three",
            "rect",
            "趋势柱三",
            {"x": 568, "y": 470, "width": 48, "height": 140, "radius": 12},
            "#fbbc04",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.chart.bar", "ui_wireframe"],
            z_index=17,
            role="chart_bar",
        ),
        _object(
            "ui-cta-button",
            "rect",
            "主行动按钮",
            {"x": 708, "y": 566, "width": 198, "height": 68, "radius": 34},
            "#1a73e8",
            stroke="#185abc",
            stroke_width=2,
            layer_id="middle",
            group_id="ui-wireframe",
            semantic_tags=["ui.cta", "ui_wireframe"],
            z_index=18,
            role="cta",
        ),
        _object(
            "ui-cta-text",
            "text",
            "主行动文字",
            {"x": 807, "y": 603, "content": "新建作品", "fontSize": 24},
            "#ffffff",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="ui-wireframe",
            semantic_tags=["ui.cta.text", "ui_wireframe"],
            z_index=19,
            role="cta_label",
        ),
    ]
    relations = [
        AgentSceneRelation(subject="ui-sidebar", relation="left_of", target="ui-hero-card", note="导航位于主内容左侧"),
        AgentSceneRelation(subject="ui-topbar", relation="above", target="ui-hero-card", note="顶部栏位于主内容上方"),
        AgentSceneRelation(subject="ui-cta-button", relation="below", target="ui-metric-card", note="行动按钮位于指标卡片下方"),
    ]
    return AgentSceneGraph(
        intent="compose_ui_wireframe",
        domain="ui_wireframe_scene",
        summary=summary,
        background="#f8fafc",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _org_chart_scene_graph(text: str) -> AgentSceneGraph:
    title = "产品团队组织结构图" if "产品" in text else "团队组织结构图"
    top_role = "负责人"
    middle_roles = ["产品组", "设计组", "研发组"]
    bottom_roles = ["用户研究", "交互设计", "前端开发", "后端开发"]
    summary = "绘制团队组织结构图, 包含负责人、职能小组和执行角色"

    objects = [
        _object(
            "org-title",
            "text",
            "组织结构图标题",
            {"x": 512, "y": 92, "content": title, "fontSize": 36},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="org-chart",
            semantic_tags=["org_chart.title", "org_chart"],
            z_index=30,
        ),
        _object(
            "org-lead-card",
            "rect",
            "负责人卡片",
            {"x": 422, "y": 145, "width": 180, "height": 82, "radius": 18},
            "#e8f0fe",
            stroke="#1a73e8",
            stroke_width=3,
            layer_id="middle",
            group_id="org-chart",
            semantic_tags=["org_chart.node", "org_chart.lead", "org_chart"],
            z_index=0,
            role="lead_node",
        ),
        _object(
            "org-lead-label",
            "text",
            "负责人标签",
            {"x": 512, "y": 188, "content": top_role, "fontSize": 24},
            "#174ea6",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="org-chart",
            semantic_tags=["org_chart.label", "org_chart.lead", "org_chart"],
            z_index=1,
            role="node_label",
        ),
        _object(
            "org-main-connector",
            "line",
            "主层级连接线",
            {"x1": 512, "y1": 227, "x2": 512, "y2": 288},
            "transparent",
            stroke="#5f6368",
            stroke_width=4,
            layer_id="middle",
            group_id="org-chart",
            semantic_tags=["org_chart.connector", "org_chart"],
            z_index=2,
            role="connector",
        ),
        _object(
            "org-branch-connector",
            "line",
            "部门横向连接线",
            {"x1": 232, "y1": 288, "x2": 792, "y2": 288},
            "transparent",
            stroke="#5f6368",
            stroke_width=4,
            layer_id="middle",
            group_id="org-chart",
            semantic_tags=["org_chart.connector", "org_chart"],
            z_index=3,
            role="connector",
        ),
    ]

    department_positions = [172, 422, 672]
    for index, role_name in enumerate(middle_roles):
        x = department_positions[index]
        objects.append(
            _object(
                f"org-dept-card-{index + 1}",
                "rect",
                f"{role_name}卡片",
                {"x": x, "y": 315, "width": 180, "height": 76, "radius": 18},
                ["#e6f4ea", "#fef7e0", "#fce8e6"][index],
                stroke=["#34a853", "#fbbc04", "#ea4335"][index],
                stroke_width=3,
                layer_id="middle",
                group_id="org-chart",
                semantic_tags=["org_chart.node", "org_chart.department", f"org_chart.department.{index + 1}", "org_chart"],
                z_index=4 + index * 2,
                role="department_node",
            )
        )
        objects.append(
            _object(
                f"org-dept-label-{index + 1}",
                "text",
                f"{role_name}标签",
                {"x": x + 90, "y": 356, "content": role_name, "fontSize": 22},
                "#202124",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="org-chart",
                semantic_tags=["org_chart.label", "org_chart.department", f"org_chart.department.{index + 1}", "org_chart"],
                z_index=5 + index * 2,
                role="node_label",
            )
        )

    bottom_positions = [142, 342, 542, 742]
    for index, role_name in enumerate(bottom_roles):
        x = bottom_positions[index]
        objects.append(
            _object(
                f"org-role-card-{index + 1}",
                "rect",
                f"{role_name}卡片",
                {"x": x, "y": 505, "width": 140, "height": 68, "radius": 16},
                "#ffffff",
                stroke="#dadce0",
                stroke_width=2,
                layer_id="middle",
                group_id="org-chart",
                semantic_tags=["org_chart.node", "org_chart.role", f"org_chart.role.{index + 1}", "org_chart"],
                z_index=12 + index * 2,
                role="role_node",
            )
        )
        objects.append(
            _object(
                f"org-role-label-{index + 1}",
                "text",
                f"{role_name}标签",
                {"x": x + 70, "y": 541, "content": role_name, "fontSize": 18},
                "#3c4043",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="org-chart",
                semantic_tags=["org_chart.label", "org_chart.role", f"org_chart.role.{index + 1}", "org_chart"],
                z_index=13 + index * 2,
                role="node_label",
            )
        )

    objects.append(
        _object(
            "org-role-connector",
            "line",
            "执行层连接线",
            {"x1": 212, "y1": 470, "x2": 812, "y2": 470},
            "transparent",
            stroke="#9aa0a6",
            stroke_width=3,
            layer_id="middle",
            group_id="org-chart",
            semantic_tags=["org_chart.connector", "org_chart.role_connector", "org_chart"],
            z_index=20,
            role="connector",
        )
    )

    relations = [
        AgentSceneRelation(subject="org-lead-card", relation="manages", target="org-dept-card-1", note="负责人管理产品组"),
        AgentSceneRelation(subject="org-lead-card", relation="manages", target="org-dept-card-2", note="负责人管理设计组"),
        AgentSceneRelation(subject="org-lead-card", relation="manages", target="org-dept-card-3", note="负责人管理研发组"),
        AgentSceneRelation(subject="org-dept-card-1", relation="owns", target="org-role-card-1", note="产品组负责用户研究"),
        AgentSceneRelation(subject="org-dept-card-2", relation="owns", target="org-role-card-2", note="设计组负责交互设计"),
        AgentSceneRelation(subject="org-dept-card-3", relation="owns", target="org-role-card-3", note="研发组负责前端开发"),
        AgentSceneRelation(subject="org-dept-card-3", relation="owns", target="org-role-card-4", note="研发组负责后端开发"),
    ]
    return AgentSceneGraph(
        intent="compose_org_chart",
        domain="org_chart_scene",
        summary=summary,
        background="#ffffff",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _gantt_chart_scene_graph(text: str) -> AgentSceneGraph:
    title = "产品迭代甘特图" if "产品" in text else "项目排期甘特图"
    summary = "绘制项目排期甘特图, 包含时间轴、任务条、今日线和上线里程碑"
    month_labels = ["第 1 月", "第 2 月", "第 3 月"]
    task_rows = [
        ("需求梳理", 300, 270, 150, "#1a73e8"),
        ("原型设计", 440, 340, 170, "#34a853"),
        ("开发联调", 580, 410, 210, "#fbbc04"),
        ("测试上线", 740, 480, 120, "#ea4335"),
    ]

    objects = [
        _object(
            "gantt-title",
            "text",
            "甘特图标题",
            {"x": 512, "y": 82, "content": title, "fontSize": 36},
            "#202124",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="gantt-chart",
            semantic_tags=["gantt_chart.title", "gantt_chart"],
            z_index=30,
        ),
        _object(
            "gantt-subtitle",
            "text",
            "甘特图说明",
            {"x": 512, "y": 124, "content": "需求 -> 设计 -> 开发 -> 测试上线", "fontSize": 18},
            "#5f6368",
            stroke="transparent",
            stroke_width=0,
            layer_id="foreground",
            group_id="gantt-chart",
            semantic_tags=["gantt_chart.subtitle", "gantt_chart"],
            z_index=31,
        ),
        _object(
            "gantt-surface",
            "rect",
            "排期图表底板",
            {"x": 130, "y": 160, "width": 760, "height": 430, "radius": 28},
            "#ffffff",
            stroke="#dadce0",
            stroke_width=2,
            layer_id="background",
            group_id="gantt-chart",
            semantic_tags=["gantt_chart.surface", "gantt_chart"],
            z_index=-1,
            role="chart_surface",
        ),
        _object(
            "gantt-axis",
            "line",
            "时间轴",
            {"x1": 275, "y1": 230, "x2": 835, "y2": 230},
            "transparent",
            stroke="#5f6368",
            stroke_width=3,
            layer_id="middle",
            group_id="gantt-chart",
            semantic_tags=["gantt_chart.timeline", "gantt_chart"],
            z_index=1,
            role="timeline_axis",
        ),
    ]

    for index, label in enumerate(month_labels):
        objects.append(
            _object(
                f"gantt-month-label-{index + 1}",
                "text",
                f"{label}标签",
                {"x": 350 + index * 180, "y": 205, "content": label, "fontSize": 18},
                "#3c4043",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.time_label", f"gantt_chart.month.{index + 1}", "gantt_chart"],
                z_index=2 + index,
                role="time_label",
            )
        )

    for index, (task_name, x, y, width, color) in enumerate(task_rows):
        objects.append(
            _object(
                f"gantt-row-label-{index + 1}",
                "text",
                f"{task_name}行标签",
                {"x": 210, "y": y + 27, "content": task_name, "fontSize": 20},
                "#202124",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.row_label", f"gantt_chart.task.{index + 1}", "gantt_chart"],
                z_index=6 + index * 2,
                role="task_label",
            )
        )
        objects.append(
            _object(
                f"gantt-task-bar-{index + 1}",
                "rect",
                f"{task_name}任务条",
                {"x": x, "y": y, "width": width, "height": 44, "radius": 22},
                color,
                stroke="transparent",
                stroke_width=0,
                layer_id="middle",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.task_bar", f"gantt_chart.task.{index + 1}", "gantt_chart"],
                z_index=7 + index * 2,
                role="task_bar",
            )
        )

    objects.extend(
        [
            _object(
                "gantt-today-line",
                "line",
                "今日进度线",
                {"x1": 645, "y1": 250, "x2": 645, "y2": 540},
                "transparent",
                stroke="#d93025",
                stroke_width=3,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.today", "gantt_chart.timeline", "gantt_chart"],
                z_index=20,
                role="today_marker",
            ),
            _object(
                "gantt-milestone",
                "circle",
                "上线里程碑",
                {"cx": 800, "cy": 502, "radius": 18},
                "#ffffff",
                stroke="#ea4335",
                stroke_width=5,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.milestone", "gantt_chart"],
                z_index=21,
                role="milestone",
            ),
            _object(
                "gantt-milestone-label",
                "text",
                "里程碑标签",
                {"x": 800, "y": 560, "content": "上线里程碑", "fontSize": 18},
                "#3c4043",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.milestone_label", "gantt_chart"],
                z_index=22,
                role="milestone_label",
            ),
            _object(
                "gantt-legend-chip",
                "rect",
                "图例色块",
                {"x": 325, "y": 622, "width": 42, "height": 18, "radius": 9},
                "#1a73e8",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.legend", "gantt_chart"],
                z_index=23,
                role="legend_marker",
            ),
            _object(
                "gantt-legend-text",
                "text",
                "图例文字",
                {"x": 475, "y": 635, "content": "彩色条表示任务周期, 红线表示当前时间", "fontSize": 18},
                "#5f6368",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="gantt-chart",
                semantic_tags=["gantt_chart.legend_text", "gantt_chart"],
                z_index=24,
                role="legend_label",
            ),
        ]
    )

    relations = [
        AgentSceneRelation(subject="gantt-task-bar-1", relation="precedes", target="gantt-task-bar-2", note="需求梳理先于原型设计"),
        AgentSceneRelation(subject="gantt-task-bar-2", relation="precedes", target="gantt-task-bar-3", note="原型设计先于开发联调"),
        AgentSceneRelation(subject="gantt-task-bar-3", relation="precedes", target="gantt-task-bar-4", note="开发联调先于测试上线"),
        AgentSceneRelation(subject="gantt-milestone", relation="marks", target="gantt-task-bar-4", note="上线里程碑标记测试上线结束"),
    ]
    return AgentSceneGraph(
        intent="compose_gantt_chart",
        domain="gantt_chart_scene",
        summary=summary,
        background="#f8fafc",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _extract_swimlane_names(text: str) -> list[str]:
    match = re.search(r"(?:泳道(?:包括|包含|有|为|是)|包括|包含|有)([^。,.，；;]+)", text)
    if match is None:
        return list(SWIMLANE_DEFAULT_LANES)

    names: list[str] = []
    raw_names = match.group(1)
    for raw_name in re.split(r"[、,，/和与及]+", raw_names):
        name = raw_name.strip()
        name = re.sub(r"^(分别是|分别为|为|是)", "", name)
        name = re.sub(r"(泳道|部门|角色)$", "", name).strip()
        if 1 <= len(name) <= 8 and name not in names:
            names.append(name)
    if len(names) < 2:
        return list(SWIMLANE_DEFAULT_LANES)
    return names[:4]


def _split_short_chinese_list(raw_items: str, *, max_items: int) -> list[str]:
    items: list[str] = []
    for raw_item in re.split(r"[、,，/和与及]+", raw_items):
        item = raw_item.strip()
        item = re.sub(r"^(分别是|分别为|为|是)", "", item)
        item = re.sub(r"(泳道|部门|角色|节点|步骤)$", "", item).strip()
        if 1 <= len(item) <= 10 and item not in items:
            items.append(item)
    return items[:max_items]


def _extract_swimlane_step_names(text: str) -> list[str]:
    match = re.search(r"(?:流程节点|流程步骤|节点|步骤)(?:包括|包含|有|为|是)([^。,.，；;]+)", text)
    if match is None:
        return []
    return _split_short_chinese_list(match.group(1), max_items=4)


def _swimlane_step_lane_indexes(lane_count: int) -> list[int]:
    if lane_count == 2:
        return [0, 0, 1, 1]
    if lane_count == 3:
        return [0, 0, 1, 2]
    return [0, 1, 2, 3]


def _swimlane_step_name(lane_name: str, index: int) -> str:
    if lane_name == "销售" and index == 1:
        return "方案确认"
    return SWIMLANE_STEP_NAMES.get(lane_name, f"{lane_name}处理")


def _swimlane_diagram_scene_graph(text: str) -> AgentSceneGraph:
    lane_names = _extract_swimlane_names(text)
    custom_step_names = _extract_swimlane_step_names(text)
    lane_count = len(lane_names)
    lane_height = 132 if lane_count <= 3 else 104
    lane_gap = 150 if lane_count <= 3 else 116
    lane_start_y = 160 if lane_count <= 3 else 140
    lane_rows = [
        (lane_name, lane_start_y + index * lane_gap, *SWIMLANE_PALETTE[index % len(SWIMLANE_PALETTE)])
        for index, lane_name in enumerate(lane_names)
    ]
    step_lane_indexes = _swimlane_step_lane_indexes(lane_count)
    step_xs = [250, 470, 640, 760]
    steps = []
    for index, lane_index in enumerate(step_lane_indexes):
        lane_name, lane_y, _, _, step_fill = lane_rows[lane_index]
        step_name = custom_step_names[index] if index < len(custom_step_names) else _swimlane_step_name(lane_name, index)
        step_y = lane_y + round((lane_height - 58) / 2)
        steps.append(
            {
                "name": step_name,
                "x": step_xs[index],
                "y": step_y,
                "fill": step_fill,
                "note": f"{lane_name}泳道执行{step_name}",
            }
        )
    objects: list[AgentSceneObject] = []

    for index, (lane_name, y, fill, stroke, _) in enumerate(lane_rows):
        lane_id = f"swimlane-lane-{index + 1}"
        objects.append(
            _object(
                lane_id,
                "rect",
                f"{lane_name}泳道",
                {"x": 150, "y": y, "width": 760, "height": lane_height, "radius": 18},
                fill,
                stroke=stroke,
                stroke_width=2,
                layer_id="background",
                group_id="swimlane-diagram",
                semantic_tags=["swimlane_diagram.lane", f"swimlane_diagram.lane.{index + 1}", "swimlane_diagram"],
                z_index=index,
                role="swimlane",
            )
        )
        objects.append(
            _object(
                f"{lane_id}-label",
                "text",
                f"{lane_name}泳道标签",
                {"x": 90, "y": y + round(lane_height / 2) + 4, "content": lane_name, "fontSize": 24},
                "#202124",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="swimlane-diagram",
                semantic_tags=["swimlane_diagram.lane_label", f"swimlane_diagram.lane.{index + 1}", "swimlane_diagram"],
                z_index=20 + index,
                role="lane_label",
            )
        )

    for index, step in enumerate(steps):
        step_id = f"swimlane-step-{index + 1}"
        objects.append(
            _object(
                step_id,
                "rect",
                f"{step['name']}节点",
                {"x": step["x"], "y": step["y"], "width": 150, "height": 58, "radius": 16},
                step["fill"],
                stroke="#3c4043",
                stroke_width=2,
                layer_id="middle",
                group_id="swimlane-diagram",
                semantic_tags=["swimlane_diagram.step", f"swimlane_diagram.step.{index + 1}", "swimlane_diagram"],
                z_index=10 + index,
                role="process_step",
            )
        )
        objects.append(
            _object(
                f"{step_id}-label",
                "text",
                f"{step['name']}标签",
                {"x": step["x"] + 75, "y": step["y"] + 34, "content": step["name"], "fontSize": 20},
                "#202124",
                stroke="transparent",
                stroke_width=0,
                layer_id="foreground",
                group_id="swimlane-diagram",
                semantic_tags=["swimlane_diagram.step_label", f"swimlane_diagram.step.{index + 1}", "swimlane_diagram"],
                z_index=30 + index,
                role="step_label",
            )
        )

    connectors = []
    for index in range(3):
        current_step = steps[index]
        next_step = steps[index + 1]
        connectors.append(
            (
                f"swimlane-connector-{index + 1}",
                current_step["x"] + 150,
                current_step["y"] + 29,
                next_step["x"],
                next_step["y"] + 29,
                f"{current_step['name']}流转到{next_step['name']}",
            )
        )
    final_step = steps[-1]
    connectors.append(
        (
            "swimlane-connector-4",
            final_step["x"] + 75,
            final_step["y"] + 58,
            final_step["x"] + 75,
            min(620, final_step["y"] + 96),
            "流程结果回写",
        )
    )
    for index, (object_id, x1, y1, x2, y2, note) in enumerate(connectors):
        objects.append(
            _object(
                object_id,
                "line",
                f"泳道连接线{index + 1}",
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "transparent",
                stroke="#5f6368",
                stroke_width=3,
                layer_id="middle",
                group_id="swimlane-diagram",
                semantic_tags=["swimlane_diagram.connector", "swimlane_diagram"],
                z_index=5 + index,
                role="connector",
            )
        )

    relations = [
        AgentSceneRelation(subject="swimlane-step-1", relation="precedes", target="swimlane-step-2", note=steps[0]["note"]),
        AgentSceneRelation(subject="swimlane-step-2", relation="handoff", target="swimlane-step-3", note=steps[1]["note"]),
        AgentSceneRelation(subject="swimlane-step-3", relation="handoff", target="swimlane-step-4", note=steps[2]["note"]),
        AgentSceneRelation(subject="swimlane-step-4", relation="reports", target="swimlane-step-1", note=steps[3]["note"]),
    ]
    lane_summary = "、".join(lane_names)
    step_summary = "、".join(step["name"] for step in steps)
    return AgentSceneGraph(
        intent="compose_swimlane_diagram",
        domain="swimlane_diagram_scene",
        summary=f"绘制{lane_summary}泳道的跨职能流程图, 节点包括{step_summary}",
        background="#ffffff",
        objects=objects,
        relations=relations,
        confidence=0.82,
    )


def _local_scene_graph_for_text(normalized_text: str) -> AgentSceneGraph | None:
    if "泳道图" in normalized_text and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _swimlane_diagram_scene_graph(normalized_text)
    if any(keyword in normalized_text for keyword in ("甘特图", "排期图", "项目排期", "进度计划")) and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _gantt_chart_scene_graph(normalized_text)
    if any(keyword in normalized_text for keyword in ("组织结构", "组织架构", "团队架构", "团队结构")) and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _org_chart_scene_graph(normalized_text)
    if any(keyword in normalized_text for keyword in ("ui", "界面", "线框图", "原型", "草图")) and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _ui_wireframe_scene_graph(normalized_text)
    if "海报" in normalized_text and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _poster_scene_graph(normalized_text)
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
        edit_plan = build_local_edit_plan(text, normalized)
        if edit_plan is not None:
            return _validate_command_plan(edit_plan)
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
