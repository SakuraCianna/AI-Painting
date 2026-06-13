from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from pydantic import ValidationError

from .compiler import ALLOWED_OBJECT_TYPES
from .scene_graph import AgentSceneGraph


MIMO_CHAT_URL = "https://api.xiaomimimo.com/v1/chat/completions"
MIMO_PLANNER_MODEL = "mimo-v2.5-pro"
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class AgentModelError(RuntimeError):
    pass


def has_mimo_model_config() -> bool:
    return bool(os.getenv("MIMO_API_KEY"))


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


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    block_match = JSON_BLOCK_PATTERN.search(stripped)
    if block_match:
        stripped = block_match.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise AgentModelError("Drawing Agent 响应不是 JSON")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AgentModelError("Drawing Agent JSON 无法解析") from exc
    if not isinstance(payload, dict):
        raise AgentModelError("Drawing Agent JSON 顶层必须是对象")
    return payload


def _scene_graph_schema_text() -> str:
    return json.dumps(AgentSceneGraph.model_json_schema(), ensure_ascii=False)


def build_scene_graph_prompt(text: str, *, repair_context: str | None = None) -> list[dict[str, str]]:
    system_message = (
        "你是 AI Painting 的 Drawing Agent Planner。只输出 JSON, 不输出 Markdown。"
        "你的任务是把中文语音绘图要求拆成 SceneGraph v2, 而不是直接输出底层绘图操作。"
        "画布默认 1024x768。对象必须是可编辑矢量对象, 坐标必须落在画布内。"
        f"只允许这些对象类型: {','.join(sorted(ALLOWED_OBJECT_TYPES))}。"
        "复杂图形要拆成多个语义对象, 每个对象要有 name, geometry, style, layer_id, group_id 和 semantic_tags。"
        "如果无法安全理解, 设置 requires_confirmation=true 并给 clarification_question。"
        "删除、清空、大量覆盖等高风险操作必须 requires_confirmation=true。"
    )
    user_message = (
        "请按这个 JSON Schema 输出 SceneGraph v2。"
        f"Schema: {_scene_graph_schema_text()}"
        f"用户语音: {text}"
    )
    if repair_context:
        user_message += f"需要修复的上下文: {repair_context}"
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


async def _request_mimo_scene_graph(messages: list[dict[str, str]]) -> AgentSceneGraph:
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        raise AgentModelError("未配置 MIMO_API_KEY")
    payload = {
        "model": os.getenv("AI_PAINTING_MIMO_LLM_MODEL", MIMO_PLANNER_MODEL),
        "messages": messages,
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
        raise AgentModelError("Drawing Agent 规划请求网络失败") from exc
    if response.status_code >= 400:
        raise AgentModelError(f"Drawing Agent 规划请求失败: HTTP {response.status_code}")
    try:
        content = response.json()["choices"][0]["message"]["content"]
        return AgentSceneGraph.model_validate(extract_json(content))
    except (KeyError, TypeError, ValidationError) as exc:
        raise AgentModelError("Drawing Agent 响应不符合 SceneGraph v2") from exc


async def build_scene_graph_with_mimo(text: str) -> AgentSceneGraph:
    return await _request_mimo_scene_graph(build_scene_graph_prompt(text))


async def repair_scene_graph_with_mimo(text: str, scene_graph: AgentSceneGraph, validation_error: str) -> AgentSceneGraph:
    repair_context = json.dumps(
        {
            "validation_error": validation_error,
            "scene_graph": scene_graph.model_dump(),
            "repair_rules": [
                "保留用户原始意图",
                "补齐缺失对象或改为 requires_confirmation",
                "坐标和尺寸必须在 1024x768 画布内",
                "关系 subject 和 target 必须引用已存在 object_id",
            ],
        },
        ensure_ascii=False,
    )
    return await _request_mimo_scene_graph(build_scene_graph_prompt(text, repair_context=repair_context))
