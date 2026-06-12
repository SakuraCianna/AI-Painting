from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from pydantic import ValidationError

from .command_parser import normalize_text
from .schemas import CommandPlan


MIMO_CHAT_URL = "https://api.xiaomimimo.com/v1/chat/completions"
MIMO_PLANNER_MODEL = "mimo-v2.5-pro"
COMPLEX_HINTS = ("然后", "并且", "同时", "接着", "再", "之后", "最后", "一排", "围绕", "组合", "场景")
ALLOWED_OPERATION_TYPES = {
    "create_canvas",
    "add_object",
    "set_style",
    "set_style_many",
    "set_metadata",
    "set_metadata_many",
    "move_object",
    "move_many",
    "scale_object",
    "scale_many",
    "delete_object",
    "save_artwork",
    "export_artwork",
    "undo",
    "redo",
}
ALLOWED_OBJECT_TYPES = {"rect", "circle", "ellipse", "triangle", "line", "arrow", "star", "text", "polygon", "path", "bezier"}
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LlmPlannerError(RuntimeError):
    pass


def is_llm_planner_enabled() -> bool:
    return os.getenv("AI_PAINTING_ENABLE_LLM_PLANNER", "false").strip().lower() in {"1", "true", "yes", "on"}


def should_use_llm_planner(text: str, rule_plan: CommandPlan) -> bool:
    if not is_llm_planner_enabled() or not os.getenv("MIMO_API_KEY"):
        return False
    normalized = normalize_text(text)
    if rule_plan.requires_confirmation and rule_plan.confidence <= 0.45:
        return True
    if any(hint in normalized for hint in COMPLEX_HINTS) and len(rule_plan.operations) <= 1:
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
        raise LlmPlannerError("MiMo 规划响应不是 JSON")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LlmPlannerError("MiMo 规划 JSON 无法解析") from exc
    if not isinstance(payload, dict):
        raise LlmPlannerError("MiMo 规划 JSON 顶层必须是对象")
    return payload


def _validate_plan(plan: CommandPlan) -> CommandPlan:
    if len(plan.operations) > _read_int_env("AI_PAINTING_LLM_MAX_OPERATIONS", 8):
        raise LlmPlannerError("MiMo 规划步骤过多")
    for operation in plan.operations:
        if operation.operation_type not in ALLOWED_OPERATION_TYPES:
            raise LlmPlannerError(f"MiMo 规划包含不支持的操作: {operation.operation_type}")
        obj = operation.payload.get("object")
        if isinstance(obj, dict) and obj.get("type") not in ALLOWED_OBJECT_TYPES:
            raise LlmPlannerError(f"MiMo 规划包含不支持的对象: {obj.get('type')}")
    if not plan.operations and not plan.requires_confirmation:
        raise LlmPlannerError("MiMo 规划没有可执行操作")
    plan.confidence = min(plan.confidence, 0.82)
    return plan


def _build_prompt(text: str) -> list[dict[str, str]]:
    schema_hint = {
        "raw_text": text,
        "normalized_text": normalize_text(text),
        "operations": [
            {
                "operation_type": "add_object",
                "payload": {
                    "object": {
                        "type": "circle",
                        "name": "圆形",
                        "layer_id": "base",
                        "group_id": None,
                        "semantic_tags": ["shape.circle"],
                        "transform": {},
                        "geometry": {"cx": 512, "cy": 384, "radius": 80},
                        "style": {"fill": "#2563eb", "stroke": "#2563eb", "strokeWidth": 2, "opacity": 1},
                    }
                },
            }
        ],
        "confidence": 0.72,
        "scene_plan": {
            "intent": "compose_scene",
            "summary": "绘制一个圆形",
            "steps": [{"step_id": "step-1", "title": "添加圆形", "intent": "add_object", "target": {}, "operation_indexes": [0]}],
            "expected_object_count": 1,
        },
        "requires_confirmation": False,
        "clarification_question": None,
        "risk_level": "low",
    }
    return [
        {
            "role": "system",
            "content": (
                "你是语音绘图工具的指令规划器。只输出 JSON, 不输出 Markdown。"
                "画布尺寸默认 1024x768。你只能使用这些对象类型: rect,circle,ellipse,triangle,line,arrow,star,text,polygon,path,bezier。"
                "你只能使用这些操作: create_canvas,add_object,set_style,set_style_many,set_metadata,set_metadata_many,move_object,move_many,scale_object,scale_many,delete_object,save_artwork,export_artwork,undo,redo。"
                "对象可以带 layer_id, group_id, semantic_tags 和 transform。target 可以按 selector,type,color,layer_id,group_id,semantic_tag 选择对象。"
                "如果用户要求清空或删除大量内容, requires_confirmation 必须为 true。"
                "无法安全理解时返回 requires_confirmation true 和 clarification_question。"
            ),
        },
        {
            "role": "user",
            "content": (
                "把下面中文语音指令拆成绘图操作计划。"
                f"输出字段必须匹配这个示例结构: {json.dumps(schema_hint, ensure_ascii=False)}"
                f"用户指令: {text}"
            ),
        },
    ]


async def plan_with_mimo(text: str) -> CommandPlan:
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        raise LlmPlannerError("未配置 MIMO_API_KEY")

    payload = {
        "model": os.getenv("AI_PAINTING_MIMO_LLM_MODEL", MIMO_PLANNER_MODEL),
        "messages": _build_prompt(text),
        "max_completion_tokens": _read_int_env("AI_PAINTING_MIMO_LLM_MAX_TOKENS", 1200),
        "temperature": _read_float_env("AI_PAINTING_MIMO_LLM_TEMPERATURE", 0.2),
        "top_p": _read_float_env("AI_PAINTING_MIMO_LLM_TOP_P", 0.9),
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    timeout = _read_float_env("AI_PAINTING_MIMO_LLM_TIMEOUT", 18.0)
    url = os.getenv("AI_PAINTING_MIMO_LLM_URL", MIMO_CHAT_URL)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise LlmPlannerError("MiMo 规划请求网络失败") from exc
    if response.status_code >= 400:
        raise LlmPlannerError(f"MiMo 规划请求失败: HTTP {response.status_code}")

    content = response.json()["choices"][0]["message"]["content"]
    try:
        plan = CommandPlan.model_validate(_extract_json(content))
    except (KeyError, TypeError, ValidationError) as exc:
        raise LlmPlannerError("MiMo 规划响应不符合 CommandPlan") from exc
    return _validate_plan(plan)
