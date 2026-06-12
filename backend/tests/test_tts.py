from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.schemas import TtsSynthesisResponse
from app.tts import build_xiaomi_tts_payload


def test_xiaomi_tts_payload_puts_text_in_assistant_message(monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_MODEL", "mimo-v2-tts")
    monkeypatch.setenv("AI_PAINTING_MIMO_TTS_VOICE", "default_zh")

    payload = build_xiaomi_tts_payload("已添加圆形", style="自然 清晰")

    assert payload["model"] == "mimo-v2-tts"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["content"] == "<style>自然 清晰</style>已添加圆形"
    assert payload["audio"] == {"format": "wav", "voice": "default_zh"}


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
