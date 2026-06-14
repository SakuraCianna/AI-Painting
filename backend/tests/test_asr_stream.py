from __future__ import annotations

from fastapi.testclient import TestClient

from app.asr import parse_audio_data_url
from app.schemas import AsrTranscriptionMetrics, AsrTranscriptionResponse


def test_streaming_asr_session_builds_wav_data_url_from_pcm16_chunks() -> None:
    from app.asr_stream import StreamingAsrSession

    session = StreamingAsrSession(language="zh", sample_rate=16000, max_audio_bytes=16)

    session.append_pcm16(b"\x00\x00\xff\x7f")
    data_url = session.to_wav_data_url()

    payload = parse_audio_data_url(data_url)
    assert payload.mime_type == "audio/wav"
    assert payload.audio_bytes[:4] == b"RIFF"
    assert payload.audio_bytes[8:12] == b"WAVE"
    assert payload.audio_bytes.endswith(b"\x00\x00\xff\x7f")
    assert session.received_bytes == 4


def test_streaming_asr_session_rejects_bad_pcm_and_oversized_audio() -> None:
    from app.asr_stream import StreamingAsrProtocolError, StreamingAsrSession

    session = StreamingAsrSession(language="zh", sample_rate=16000, max_audio_bytes=4)

    try:
        session.append_pcm16(b"\x00")
    except StreamingAsrProtocolError as exc:
        assert "PCM16" in str(exc)
    else:
        raise AssertionError("odd PCM16 payload should be rejected")

    session.append_pcm16(b"\x00\x00\x01\x00")
    try:
        session.append_pcm16(b"\x02\x00")
    except StreamingAsrProtocolError as exc:
        assert "过大" in str(exc)
    else:
        raise AssertionError("oversized stream should be rejected")


def test_asr_stream_websocket_transcribes_pcm_chunks(client: TestClient, monkeypatch) -> None:
    from app import main

    async def fake_transcribe(audio_data_url: str, language: str = "zh") -> AsrTranscriptionResponse:
        payload = parse_audio_data_url(audio_data_url)
        assert language == "zh"
        assert payload.audio_bytes.endswith(b"\x00\x00\xff\x7f")
        return AsrTranscriptionResponse(
            text="画一个蓝色圆形",
            provider="xiaomi",
            provider_label="小米 MiMo ASR",
            attempts=[],
            metrics=AsrTranscriptionMetrics(
                total_ms=321,
                audio_bytes=len(payload.audio_bytes),
                attempt_count=1,
                successful_provider="xiaomi",
                fallback_count=0,
            ),
        )

    monkeypatch.setattr(main, "transcribe_audio_data_url", fake_transcribe)

    with client.websocket_connect("/api/asr/stream") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "start", "language": "zh", "sample_rate": 16000})
        assert websocket.receive_json()["type"] == "started"
        websocket.send_bytes(b"\x00\x00\xff\x7f")
        received = websocket.receive_json()
        assert received["type"] == "audio_received"
        assert received["audio_bytes"] == 4
        websocket.send_json({"type": "finalize"})
        assert websocket.receive_json()["type"] == "recognizing"
        final = websocket.receive_json()

    assert final["type"] == "final"
    assert final["text"] == "画一个蓝色圆形"
    assert final["provider"] == "xiaomi"
    assert final["metrics"]["successful_provider"] == "xiaomi"


def test_asr_stream_websocket_reports_empty_audio(client: TestClient, monkeypatch) -> None:
    from app import main

    async def fail_if_called(_: str, language: str = "zh") -> AsrTranscriptionResponse:
        raise AssertionError("empty stream should not call ASR provider")

    monkeypatch.setattr(main, "transcribe_audio_data_url", fail_if_called)

    with client.websocket_connect("/api/asr/stream") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "start", "language": "zh", "sample_rate": 16000})
        assert websocket.receive_json()["type"] == "started"
        websocket.send_json({"type": "finalize"})
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "empty_audio"
