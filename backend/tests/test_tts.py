from __future__ import annotations

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from app.schemas import TtsSynthesisResponse
from app.tts import TtsProviderError, _extract_audio_data, _format_tts_text, build_xiaomi_tts_payload, synthesize_with_xiaomi


def test_xiaomi_tts_payload_puts_text_in_assistant_message(monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_MODEL", "mimo-v2-tts")
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_VOICE", "default_zh")

    payload = build_xiaomi_tts_payload("已添加圆形", style="自然 清晰")

    assert payload["model"] == "mimo-v2-tts"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["content"] == "<style>自然 清晰</style>已添加圆形"
    assert payload["audio"] == {"format": "wav", "voice": "default_zh"}


def test_tts_payload_validates_text_and_custom_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_MODEL", "custom-tts")

    payload = build_xiaomi_tts_payload("  已完成  ", voice="voice-a", style=None)

    assert payload["model"] == "custom-tts"
    assert payload["messages"][1]["content"] == "已完成"
    assert payload["audio"]["voice"] == "voice-a"

    with pytest.raises(ValueError, match="不能为空"):
        _format_tts_text("   ", None)


def test_extract_audio_data_accepts_valid_base64_and_rejects_bad_payload() -> None:
    encoded = base64.b64encode(b"RIFF").decode("ascii")

    assert _extract_audio_data({"choices": [{"message": {"audio": {"data": encoded}}}]}) == encoded

    with pytest.raises(TtsProviderError, match="没有音频数据"):
        _extract_audio_data({"choices": []})
    with pytest.raises(TtsProviderError, match="为空"):
        _extract_audio_data({"choices": [{"message": {"audio": {"data": "   "}}}]})
    with pytest.raises(TtsProviderError, match="Base64"):
        _extract_audio_data({"choices": [{"message": {"audio": {"data": "not-base64"}}}]})


class _FakeTtsResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_synthesize_with_xiaomi_success_and_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = base64.b64encode(b"RIFF").decode("ascii")
    responses = [
        _FakeTtsResponse(200, {"choices": [{"message": {"audio": {"data": encoded}}}]}),
        _FakeTtsResponse(429, {"error": "rate limited"}),
    ]
    calls: list[dict[str, object]] = []

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers, json):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return responses.pop(0)

    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_URL", "https://tts.example/v1")
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_TIMEOUT", "4.5")
    monkeypatch.setattr("app.tts.httpx.AsyncClient", FakeAsyncClient)

    response = asyncio.run(synthesize_with_xiaomi("已完成"))

    assert response.audio_data_url == f"data:audio/wav;base64,{encoded}"
    assert calls[0]["url"] == "https://tts.example/v1"
    assert calls[0]["headers"]["api-key"] == "test-key"

    with pytest.raises(TtsProviderError, match="HTTP 429"):
        asyncio.run(synthesize_with_xiaomi("已完成"))


def test_synthesize_with_xiaomi_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)

    with pytest.raises(TtsProviderError, match="MIMO_API_KEY"):
        asyncio.run(synthesize_with_xiaomi("已完成"))


def test_tts_endpoint_returns_audio_data_url(client: TestClient, monkeypatch) -> None:
    from app import main

    async def fake_synthesize(text: str, voice: str | None = None, style: str | None = None) -> TtsSynthesisResponse:
        audio_base64 = base64.b64encode(b"RIFF").decode("ascii")
        return TtsSynthesisResponse(audio_data_url=f"data:audio/wav;base64,{audio_base64}")

    monkeypatch.setattr(main, "synthesize_with_xiaomi", fake_synthesize)

    response = client.post("/api/tts/synthesize", json={"text": "已添加圆形"})

    assert response.status_code == 200
    assert response.json()["provider"] == "xiaomi"
    assert response.json()["audio_data_url"].startswith("data:audio/wav;base64,")
