from __future__ import annotations

import asyncio
import json as json_module
from typing import Any

import pytest

from app.agent.model_client import (
    AgentModelError,
    _request_mimo_scene_graph,
    build_scene_graph_prompt,
    extract_json,
    has_mimo_model_config,
)


def test_extract_json_accepts_fenced_and_noisy_content() -> None:
    assert extract_json('```json\n{"summary": "ok"}\n```') == {"summary": "ok"}
    assert extract_json('前缀 {"summary": "ok", "objects": []} 后缀') == {"summary": "ok", "objects": []}

    with pytest.raises(AgentModelError, match="不是 JSON"):
        extract_json("没有结构化内容")
    with pytest.raises(AgentModelError, match="无法解析"):
        extract_json("{bad json}")


def test_build_scene_graph_prompt_includes_schema_and_repair_context() -> None:
    messages = build_scene_graph_prompt("画一个流程图", repair_context="缺少对象 id")

    assert messages[0]["role"] == "system"
    assert "Drawing Agent Planner" in messages[0]["content"]
    assert "SceneGraph v2" in messages[1]["content"]
    assert "画一个流程图" in messages[1]["content"]
    assert "缺少对象 id" in messages[1]["content"]


def test_has_mimo_model_config_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    assert has_mimo_model_config() is False

    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    assert has_mimo_model_config() is True


class _FakeModelResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def test_request_mimo_scene_graph_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "summary": "一个蓝色圆形",
        "objects": [
            {
                "object_id": "circle-1",
                "type": "circle",
                "name": "蓝色圆形",
                "geometry": {"cx": 512, "cy": 384, "radius": 80},
                "style": {"fill": "#2563eb", "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
                "semantic_tags": ["shape.circle"],
            }
        ],
    }
    calls: list[dict[str, Any]] = []

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers, json: dict[str, Any]):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return _FakeModelResponse(
                200,
                {"choices": [{"message": {"content": json_module.dumps(payload, ensure_ascii=False)}}]},
            )

    monkeypatch.setenv("MIMO_API_KEY", "model-key")
    monkeypatch.setenv("AI_PAINTING_MIMO_LLM_URL", "https://model.example/v1/chat/completions")
    monkeypatch.setenv("AI_PAINTING_MIMO_LLM_TIMEOUT", "6.5")
    monkeypatch.setenv("AI_PAINTING_MIMO_LLM_MAX_TOKENS", "1000")
    monkeypatch.setenv("AI_PAINTING_MIMO_LLM_TEMPERATURE", "0.2")
    monkeypatch.setattr("app.agent.model_client.httpx.AsyncClient", FakeAsyncClient)

    scene_graph = asyncio.run(_request_mimo_scene_graph([{"role": "user", "content": "画圆"}]))

    assert scene_graph.summary == "一个蓝色圆形"
    assert scene_graph.objects[0].object_id == "circle-1"
    assert calls[0]["url"] == "https://model.example/v1/chat/completions"
    assert calls[0]["headers"]["api-key"] == "model-key"
    assert calls[0]["json"]["max_completion_tokens"] == 1000


def test_request_mimo_scene_graph_reports_configuration_http_and_schema_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    with pytest.raises(AgentModelError, match="MIMO_API_KEY"):
        asyncio.run(_request_mimo_scene_graph([{"role": "user", "content": "画圆"}]))

    responses = [
        _FakeModelResponse(500, {"error": "server"}),
        _FakeModelResponse(200, {"choices": [{"message": {"content": '{"objects": "bad"}'}}]}),
    ]

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers, json):
            return responses.pop(0)

    monkeypatch.setenv("MIMO_API_KEY", "model-key")
    monkeypatch.setattr("app.agent.model_client.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(AgentModelError, match="HTTP 500"):
        asyncio.run(_request_mimo_scene_graph([{"role": "user", "content": "画圆"}]))
    with pytest.raises(AgentModelError, match="不符合 SceneGraph"):
        asyncio.run(_request_mimo_scene_graph([{"role": "user", "content": "画圆"}]))
