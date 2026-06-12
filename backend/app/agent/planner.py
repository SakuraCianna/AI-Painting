from __future__ import annotations

import importlib.util
import json
import os
import re
from typing import Any, TypedDict

import httpx
from pydantic import ValidationError

from ..command_parser import is_voice_noise_input, normalize_text
from ..schemas import CommandPlan
from .compiler import ALLOWED_OBJECT_TYPES, ALLOWED_OPERATION_TYPES, SceneGraphCompileError, compile_scene_graph_to_command_plan
from .scene_graph import AgentSceneGraph, AgentSceneObject, AgentSceneRelation, AgentStyle


MIMO_CHAT_URL = "https://api.xiaomimimo.com/v1/chat/completions"
MIMO_PLANNER_MODEL = "mimo-v2.5-pro"
COMPLEX_HINTS = ("然后", "并且", "同时", "接着", "再", "之后", "最后", "一排", "围绕", "组合", "场景")
AGENT_SCENE_HINTS = ("客厅", "卧室", "厨房", "办公室", "教室", "城市", "花园", "海报", "信息图", "流程图", "结构图")
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class DrawingAgentError(RuntimeError):
    pass


class AgentState(TypedDict, total=False):
    text: str
    normalized_text: str
    scene_graph: AgentSceneGraph
    plan: CommandPlan


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
    if not os.getenv("MIMO_API_KEY"):
        return False
    if rule_plan.requires_confirmation and rule_plan.confidence <= 0.45:
        return True
    if any(hint in normalized for hint in COMPLEX_HINTS + AGENT_SCENE_HINTS) and len(rule_plan.operations) <= 1:
        return True
    return False


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    block_match = JSON_BLOCK_PATTERN.search(stripped)
    if block_match:
        stripped = block_match.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise DrawingAgentError("Drawing Agent 响应不是 JSON")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DrawingAgentError("Drawing Agent JSON 无法解析") from exc
    if not isinstance(payload, dict):
        raise DrawingAgentError("Drawing Agent JSON 顶层必须是对象")
    return payload


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


def _local_scene_graph_for_text(normalized_text: str) -> AgentSceneGraph | None:
    if "客厅" in normalized_text and any(keyword in normalized_text for keyword in ("画", "创建", "生成")):
        return _living_room_scene_graph(normalized_text)
    return None


def _langgraph_is_available() -> bool:
    return importlib.util.find_spec("langgraph") is not None


def _compile_local_scene_with_optional_graph(raw_text: str, normalized_text: str, graph: AgentSceneGraph) -> CommandPlan:
    if not _langgraph_is_available():
        return compile_scene_graph_to_command_plan(raw_text, normalized_text, graph)

    try:
        from langgraph.graph import END, START, StateGraph

        builder = StateGraph(AgentState)
        builder.add_node("compile_scene_graph", lambda state: {"plan": compile_scene_graph_to_command_plan(state["text"], state["normalized_text"], state["scene_graph"])})
        builder.add_edge(START, "compile_scene_graph")
        builder.add_edge("compile_scene_graph", END)
        runtime = builder.compile()
        result = runtime.invoke({"text": raw_text, "normalized_text": normalized_text, "scene_graph": graph})
        return result["plan"]
    except Exception:
        return compile_scene_graph_to_command_plan(raw_text, normalized_text, graph)


def _build_scene_graph_prompt(text: str) -> list[dict[str, str]]:
    schema_hint = AgentSceneGraph.model_json_schema()
    return [
        {
            "role": "system",
            "content": (
                "你是 AI Painting 的 Drawing Agent Planner。只输出 JSON, 不输出 Markdown。"
                "你的任务是把中文语音绘图要求拆成 SceneGraph v2, 而不是直接输出底层绘图操作。"
                "画布默认 1024x768。对象必须是可编辑矢量对象, 坐标必须落在画布内。"
                f"只允许这些对象类型: {','.join(sorted(ALLOWED_OBJECT_TYPES))}。"
                "复杂图形要拆成多个语义对象, 每个对象要有 name, geometry, style, layer_id, group_id 和 semantic_tags。"
                "如果无法安全理解, 设置 requires_confirmation=true 并给 clarification_question。"
                "删除、清空、大量覆盖等高风险操作必须 requires_confirmation=true。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按这个 JSON Schema 输出 SceneGraph v2。"
                f"Schema: {json.dumps(schema_hint, ensure_ascii=False)}"
                f"用户语音: {text}"
            ),
        },
    ]


async def _scene_graph_with_mimo(text: str) -> AgentSceneGraph:
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        raise DrawingAgentError("未配置 MIMO_API_KEY")
    payload = {
        "model": os.getenv("AI_PAINTING_MIMO_LLM_MODEL", MIMO_PLANNER_MODEL),
        "messages": _build_scene_graph_prompt(text),
        "max_completion_tokens": _read_int_env("AI_PAINTING_MIMO_LLM_MAX_TOKENS", 1600),
        "temperature": _read_float_env("AI_PAINTING_MIMO_LLM_TEMPERATURE", 0.18),
        "top_p": _read_float_env("AI_PAINTING_MIMO_LLM_TOP_P", 0.9),
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    timeout = _read_float_env("AI_PAINTING_MIMO_LLM_TIMEOUT", 18.0)
    url = os.getenv("AI_PAINTING_MIMO_LLM_URL", MIMO_CHAT_URL)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise DrawingAgentError("Drawing Agent 规划请求网络失败") from exc
    if response.status_code >= 400:
        raise DrawingAgentError(f"Drawing Agent 规划请求失败: HTTP {response.status_code}")
    try:
        content = response.json()["choices"][0]["message"]["content"]
        return AgentSceneGraph.model_validate(_extract_json(content))
    except (KeyError, TypeError, ValidationError) as exc:
        raise DrawingAgentError("Drawing Agent 响应不符合 SceneGraph v2") from exc


async def plan_with_drawing_agent(text: str, *, rule_plan: CommandPlan | None = None) -> CommandPlan:
    normalized = normalize_text(text)
    try:
        scene_graph = _local_scene_graph_for_text(normalized)
        if scene_graph is None:
            scene_graph = await _scene_graph_with_mimo(text)
        plan = _compile_local_scene_with_optional_graph(text, normalized, scene_graph)
        return _validate_command_plan(plan)
    except (SceneGraphCompileError, ValidationError) as exc:
        raise DrawingAgentError("Drawing Agent 计划校验失败") from exc
