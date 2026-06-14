from __future__ import annotations

import asyncio
import base64
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.asr import (
    AsrProviderError,
    AsrProvidersUnavailable,
    _extract_text_from_json,
    _transcribe_with_local_command,
    _transcribe_with_local_url,
    build_xiaomi_payload,
    get_asr_provider_status,
    parse_audio_data_url,
    transcribe_audio_data_url,
)
from app.schemas import AsrTranscriptionResponse


def test_parse_audio_data_url_accepts_wav() -> None:
    audio_bytes = b"RIFF"
    data_url = f"data:audio/wav;base64,{base64.b64encode(audio_bytes).decode('ascii')}"

    payload = parse_audio_data_url(data_url)

    assert payload.mime_type == "audio/wav"
    assert payload.extension == ".wav"
    assert payload.audio_bytes == audio_bytes


def test_parse_audio_data_url_accepts_mp3_and_rejects_invalid_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    mp3_data = base64.b64encode(b"ID3").decode("ascii")
    payload = parse_audio_data_url(f"data:audio/mpeg;base64,{mp3_data}")

    assert payload.extension == ".mp3"

    with pytest.raises(ValueError, match="data"):
        parse_audio_data_url("plain-text")
    with pytest.raises(ValueError, match="wav 或 mp3"):
        parse_audio_data_url("data:video/mp4;base64,AAAA")
    with pytest.raises(ValueError, match="Base64"):
        parse_audio_data_url("data:audio/wav;base64,***")

    monkeypatch.setenv("AI_PAINTING_ASR_MAX_AUDIO_BYTES", "2")
    with pytest.raises(ValueError, match="过大"):
        parse_audio_data_url(f"data:audio/wav;base64,{base64.b64encode(b'abc').decode('ascii')}")


def test_extract_text_from_supported_asr_response_shapes() -> None:
    assert _extract_text_from_json({"text": "  画圆  "}) == "画圆"
    assert _extract_text_from_json({"result": {"transcript": "画矩形"}}) == "画矩形"
    assert _extract_text_from_json({"data": {"content": "画星星"}}) == "画星星"
    assert _extract_text_from_json({"choices": [{"message": {"content": "画房子"}}]}) == "画房子"

    with pytest.raises(AsrProviderError, match="没有可用文本"):
        _extract_text_from_json({"data": []})


def test_xiaomi_payload_matches_mimo_asr_contract() -> None:
    payload = build_xiaomi_payload("data:audio/wav;base64,AAAA", "zh", model="mimo-v2.5-asr")

    assert payload["model"] == "mimo-v2.5-asr"
    assert payload["asr_options"]["language"] == "zh"
    input_audio = payload["messages"][0]["content"][0]
    assert input_audio["type"] == "input_audio"
    assert input_audio["input_audio"]["data"] == "data:audio/wav;base64,AAAA"


def test_xiaomi_payload_rejects_unsafe_language() -> None:
    try:
        build_xiaomi_payload("data:audio/wav;base64,AAAA", "zh&calc")
    except ValueError as exc:
        assert "ASR 语种" in str(exc)
    else:
        raise AssertionError("unsafe language should be rejected")


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
    assert status.provider_capabilities["xiaomi"].mode == "segment"
    assert status.provider_capabilities["xiaomi"].streaming_supported is False
    assert status.provider_capabilities["xiaomi"].interim_results_supported is False
    assert status.provider_capabilities["xiaomi"].segment_submission is True
    assert status.provider_capabilities["xiaomi"].websocket_transport_supported is True
    assert status.provider_capabilities["xiaomi"].partial_transcript_supported is False
    assert status.provider_capabilities["xiaomi"].silence_stop_ms == 1500
    assert status.provider_capabilities["local"].mode == "segment"
    assert status.provider_capabilities["local"].websocket_transport_supported is True
    assert status.provider_capabilities["web_speech"].mode == "browser_interim"
    assert status.provider_capabilities["web_speech"].streaming_supported is True
    assert status.provider_capabilities["web_speech"].interim_results_supported is True
    assert status.provider_capabilities["web_speech"].websocket_transport_supported is False
    assert status.provider_capabilities["web_speech"].partial_transcript_supported is True
    assert status.provider_capabilities["web_speech"].segment_submission is False


class _FakeAsrResponse:
    def __init__(self, status_code: int, *, json_body=None, text: str = "", content_type: str = "application/json") -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text
        self.headers = {"content-type": content_type}

    def json(self):
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body


def test_local_asr_url_accepts_json_and_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeAsrResponse(200, json_body={"text": "本地识别"}),
        _FakeAsrResponse(200, text="纯文本识别", content_type="text/plain"),
    ]
    calls: list[dict[str, object]] = []

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, files, data):
            calls.append({"url": url, "files": files, "data": data, "timeout": self.timeout})
            return responses.pop(0)

    audio = parse_audio_data_url("data:audio/wav;base64,AAAA")
    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_URL", "http://127.0.0.1:9001/asr")
    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_TIMEOUT", "3.5")
    monkeypatch.setattr("app.asr.httpx.AsyncClient", FakeAsyncClient)

    assert asyncio.run(_transcribe_with_local_url(audio, "zh")) == "本地识别"
    assert asyncio.run(_transcribe_with_local_url(audio, "zh")) == "纯文本识别"
    assert calls[0]["url"] == "http://127.0.0.1:9001/asr"
    assert calls[0]["data"] == {"language": "zh"}


def test_local_asr_url_reports_http_and_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeAsrResponse(500, json_body={"text": "失败"}),
        _FakeAsrResponse(200, text="   ", content_type="text/plain"),
    ]

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, files, data):
            return responses.pop(0)

    audio = parse_audio_data_url("data:audio/wav;base64,AAAA")
    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_URL", "http://127.0.0.1:9001/asr")
    monkeypatch.setattr("app.asr.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(AsrProviderError, match="HTTP 500"):
        asyncio.run(_transcribe_with_local_url(audio, "zh"))
    with pytest.raises(AsrProviderError, match="没有返回文本"):
        asyncio.run(_transcribe_with_local_url(audio, "zh"))


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


def test_transcribe_endpoint_rejects_unsafe_language(client: TestClient) -> None:
    response = client.post(
        "/api/asr/transcribe",
        json={"audio_data_url": "data:audio/wav;base64,AAAA", "language": "zh&calc"},
    )

    assert response.status_code == 400


def test_local_asr_command_runs_without_shell(monkeypatch) -> None:
    audio = parse_audio_data_url("data:audio/wav;base64,AAAA")
    captured: dict[str, object] = {}

    def fake_run(command, *, shell, capture_output, text, timeout):
        captured["command"] = command
        captured["shell"] = shell
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(command, 0, stdout="画一个圆\n", stderr="")

    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_COMMAND", 'python local_asr.py --audio "{audio}" --language "{language}"')
    monkeypatch.setattr("app.asr.subprocess.run", fake_run)

    result = asyncio.run(_transcribe_with_local_command(audio, "zh"))

    assert result == "画一个圆"
    assert captured["shell"] is False


def test_local_asr_command_reports_failure_and_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    audio = parse_audio_data_url("data:audio/wav;base64,AAAA")
    results = [
        subprocess.CompletedProcess(["local"], 1, stdout="", stderr="模型加载失败"),
        subprocess.CompletedProcess(["local"], 0, stdout="   ", stderr=""),
    ]

    def fake_run(command, *, shell, capture_output, text, timeout):
        return results.pop(0)

    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_COMMAND", 'python local_asr.py --audio "{audio}" --language "{language}"')
    monkeypatch.setattr("app.asr.subprocess.run", fake_run)

    with pytest.raises(AsrProviderError, match="模型加载失败"):
        asyncio.run(_transcribe_with_local_command(audio, "zh"))
    with pytest.raises(AsrProviderError, match="没有输出文本"):
        asyncio.run(_transcribe_with_local_command(audio, "zh"))


def test_transcribe_audio_data_url_records_fallback_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_xiaomi(audio, language):
        raise AsrProviderError("小米临时失败")

    async def local_success(audio, language):
        return "本地识别成功"

    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setenv("AI_PAINTING_LOCAL_ASR_COMMAND", "local-asr")
    monkeypatch.setenv("AI_PAINTING_ASR_PROVIDERS", "xiaomi,local")
    monkeypatch.setattr("app.asr._transcribe_with_xiaomi", fail_xiaomi)
    monkeypatch.setattr("app.asr._transcribe_with_local", local_success)

    response = asyncio.run(transcribe_audio_data_url("data:audio/wav;base64,AAAA", "zh"))

    assert response.text == "本地识别成功"
    assert response.provider == "local"
    assert [attempt.status for attempt in response.attempts] == ["failed", "success"]
    assert response.metrics.attempt_count == 2
    assert response.metrics.fallback_count == 1


def test_transcribe_audio_data_url_raises_when_all_providers_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("AI_PAINTING_LOCAL_ASR_URL", raising=False)
    monkeypatch.delenv("AI_PAINTING_LOCAL_ASR_COMMAND", raising=False)
    monkeypatch.setenv("AI_PAINTING_ASR_PROVIDERS", "xiaomi,local")

    with pytest.raises(AsrProvidersUnavailable) as exc_info:
        asyncio.run(transcribe_audio_data_url("data:audio/wav;base64,AAAA", "zh"))

    assert [attempt.status for attempt in exc_info.value.attempts] == ["skipped", "skipped"]


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
