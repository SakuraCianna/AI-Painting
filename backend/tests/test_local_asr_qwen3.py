from __future__ import annotations

from fastapi.testclient import TestClient


def test_qwen3_local_asr_health_uses_lightweight_default(monkeypatch) -> None:
    monkeypatch.delenv("QWEN3_ASR_MODEL", raising=False)

    from local_asr_qwen3 import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["provider"] == "qwen3-asr"
    assert response.json()["model"] == "Qwen/Qwen3-ASR-0.6B"


def test_qwen3_local_asr_mock_transcription(monkeypatch) -> None:
    monkeypatch.setenv("QWEN3_ASR_MOCK_TEXT", "画一个蓝色圆形")

    from local_asr_qwen3 import app

    response = TestClient(app).post(
        "/asr",
        data={"language": "zh"},
        files={"file": ("voice.wav", b"RIFF", "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "画一个蓝色圆形"
    assert body["provider"] == "qwen3-asr"
    assert body["model"] == "Qwen/Qwen3-ASR-0.6B"
    assert body["language"] == "Chinese"
