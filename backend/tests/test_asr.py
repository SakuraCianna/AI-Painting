from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.asr import build_xiaomi_payload, get_asr_provider_status, parse_audio_data_url
from app.schemas import AsrTranscriptionResponse


def test_parse_audio_data_url_accepts_wav() -> None:
    audio_bytes = b"RIFF"
    data_url = f"data:audio/wav;base64,{base64.b64encode(audio_bytes).decode('ascii')}"

    payload = parse_audio_data_url(data_url)

    assert payload.mime_type == "audio/wav"
    assert payload.extension == ".wav"
    assert payload.audio_bytes == audio_bytes


def test_xiaomi_payload_matches_mimo_asr_contract() -> None:
    payload = build_xiaomi_payload("data:audio/wav;base64,AAAA", "zh", model="mimo-v2.5-asr")

    assert payload["model"] == "mimo-v2.5-asr"
    assert payload["asr_options"]["language"] == "zh"
    input_audio = payload["messages"][0]["content"][0]
    assert input_audio["type"] == "input_audio"
    assert input_audio["input_audio"]["data"] == "data:audio/wav;base64,AAAA"


def test_provider_status_prefers_xiaomi_then_local(monkeypatch) -> None:
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_URL", "http://127.0.0.1:9001/asr")
    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_LABEL", "Qwen3-ASR 本地服务")
    monkeypatch.setenv("AI_PAINTING_ASR_PROVIDERS", "xiaomi,local")

    status = get_asr_provider_status()

    assert status.providers == ["xiaomi", "local"]
    assert status.primary_provider == "xiaomi"
    assert status.fallback_provider == "web_speech"
    assert status.provider_labels["local"] == "Qwen3-ASR 本地服务"


def test_transcribe_endpoint_returns_503_without_backend_provider(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("AI_PAINTING_LOCAL_ASR_URL", raising=False)
    monkeypatch.delenv("AI_PAINTING_LOCAL_ASR_COMMAND", raising=False)

    response = client.post(
        "/api/asr/transcribe",
        json={"audio_data_url": "data:audio/wav;base64,AAAA", "language": "zh"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "后端 ASR 不可用, 请使用 Web Speech API 兜底"


def test_transcribe_endpoint_returns_text(client: TestClient, monkeypatch) -> None:
    from app import main

    async def fake_transcribe(audio_data_url: str, language: str = "zh") -> AsrTranscriptionResponse:
        return AsrTranscriptionResponse(
            text="画一个蓝色圆形",
            provider="xiaomi",
            provider_label="小米 MiMo ASR",
            attempts=[],
        )

    monkeypatch.setattr(main, "transcribe_audio_data_url", fake_transcribe)

    response = client.post(
        "/api/asr/transcribe",
        json={"audio_data_url": "data:audio/wav;base64,AAAA", "language": "zh"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "画一个蓝色圆形"
    assert response.json()["provider"] == "xiaomi"
    assert response.json()["metrics"]["attempt_count"] == 0
