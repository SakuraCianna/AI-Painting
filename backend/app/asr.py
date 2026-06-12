from __future__ import annotations

import asyncio
import base64
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from .schemas import AsrProviderAttempt, AsrProvidersResponse, AsrTranscriptionMetrics, AsrTranscriptionResponse


XIAOMI_ASR_URL = "https://api.xiaomimimo.com/v1/chat/completions"
XIAOMI_ASR_MODEL = "mimo-v2.5-asr"
WEB_SPEECH_PROVIDER = "web_speech"
DATA_URL_PATTERN = re.compile(r"^data:(?P<mime>[-\w.+/]+);base64,(?P<data>.+)$", re.DOTALL)
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
SUPPORTED_AUDIO_TYPES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
}
PROVIDER_LABELS = {
    "xiaomi": "小米 MiMo ASR",
    "local": "本地 ASR",
    WEB_SPEECH_PROVIDER: "Web Speech API",
}


class AsrProviderError(RuntimeError):
    pass


class AsrProvidersUnavailable(RuntimeError):
    def __init__(self, attempts: list[AsrProviderAttempt]):
        super().__init__("没有可用的后端 ASR Provider")
        self.attempts = attempts


@dataclass(frozen=True)
class AudioPayload:
    data_url: str
    mime_type: str
    audio_bytes: bytes
    extension: str


def _read_csv_env(name: str, default: str) -> list[str]:
    return [item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()]


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


def provider_label(provider: str) -> str:
    if provider == "local":
        return os.getenv("AI_PAINTING_LOCAL_ASR_LABEL", PROVIDER_LABELS["local"])
    return PROVIDER_LABELS.get(provider, provider)


def normalize_asr_language(language: str | None) -> str:
    normalized = (language or os.getenv("AI_PAINTING_ASR_LANGUAGE", "zh")).strip()
    if not LANGUAGE_PATTERN.fullmatch(normalized):
        raise ValueError("ASR 语种只能包含字母、数字、下划线或连字符")
    return normalized


def get_asr_provider_chain() -> list[str]:
    providers = _read_csv_env("AI_PAINTING_ASR_PROVIDERS", "xiaomi,local")
    return [provider for provider in providers if provider in {"xiaomi", "local"}]


def is_provider_configured(provider: str) -> bool:
    if provider == "xiaomi":
        return bool(os.getenv("MIMO_API_KEY"))
    if provider == "local":
        return bool(os.getenv("AI_PAINTING_LOCAL_ASR_URL") or os.getenv("AI_PAINTING_LOCAL_ASR_COMMAND"))
    return False


def get_asr_provider_status() -> AsrProvidersResponse:
    configured = [provider for provider in get_asr_provider_chain() if is_provider_configured(provider)]
    return AsrProvidersResponse(
        providers=configured,
        provider_labels={provider: provider_label(provider) for provider in configured + [WEB_SPEECH_PROVIDER]},
        primary_provider=configured[0] if configured else None,
        fallback_provider=WEB_SPEECH_PROVIDER,
    )


def parse_audio_data_url(audio_data_url: str) -> AudioPayload:
    match = DATA_URL_PATTERN.match(audio_data_url.strip())
    if not match:
        raise ValueError("音频数据必须使用 data:{MIME_TYPE};base64,... 格式")

    mime_type = match.group("mime").lower()
    extension = SUPPORTED_AUDIO_TYPES.get(mime_type)
    if not extension:
        raise ValueError("当前仅支持 wav 或 mp3 音频")

    try:
        audio_bytes = base64.b64decode(match.group("data"), validate=True)
    except ValueError as exc:
        raise ValueError("音频 Base64 数据无法解析") from exc

    max_bytes = _read_int_env("AI_PAINTING_ASR_MAX_AUDIO_BYTES", 7_500_000)
    if len(audio_bytes) > max_bytes:
        raise ValueError("音频片段过大, 请缩短单次语音指令")

    return AudioPayload(
        data_url=audio_data_url,
        mime_type=mime_type,
        audio_bytes=audio_bytes,
        extension=extension,
    )


def build_xiaomi_payload(audio_data_url: str, language: str, model: str | None = None) -> dict[str, Any]:
    normalized_language = normalize_asr_language(language)
    return {
        "model": model or os.getenv("AI_PAINTING_XIAOMI_ASR_MODEL", XIAOMI_ASR_MODEL),
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_data_url,
                        },
                    }
                ],
            }
        ],
        "asr_options": {
            "language": normalized_language,
        },
    }


def _extract_text_from_json(payload: dict[str, Any]) -> str:
    direct_fields = ("text", "transcript", "content")
    for field in direct_fields:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for parent_field in ("result", "data"):
        nested = payload.get(parent_field)
        if isinstance(nested, dict):
            for field in direct_fields:
                value = nested.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content.strip()

    raise AsrProviderError("ASR 响应中没有可用文本")


async def _transcribe_with_xiaomi(audio: AudioPayload, language: str) -> str:
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        raise AsrProviderError("未配置 MIMO_API_KEY")

    timeout = _read_float_env("AI_PAINTING_XIAOMI_ASR_TIMEOUT", 20.0)
    url = os.getenv("AI_PAINTING_XIAOMI_ASR_URL", XIAOMI_ASR_URL)
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = build_xiaomi_payload(audio.data_url, language)
    retries = max(0, _read_int_env("AI_PAINTING_XIAOMI_ASR_RETRIES", 1))
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 500 and attempt < retries:
                last_error = AsrProviderError(f"小米 ASR 请求失败: HTTP {response.status_code}")
                await asyncio.sleep(0.25 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise AsrProviderError(f"小米 ASR 请求失败: HTTP {response.status_code}")
            return _extract_text_from_json(response.json())
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt >= retries:
                break
            await asyncio.sleep(0.25 * (attempt + 1))
    raise AsrProviderError(f"小米 ASR 请求失败: {last_error}") from last_error


async def _transcribe_with_local_url(audio: AudioPayload, language: str) -> str:
    url = os.getenv("AI_PAINTING_LOCAL_ASR_URL")
    if not url:
        raise AsrProviderError("未配置 AI_PAINTING_LOCAL_ASR_URL")

    timeout = _read_float_env("AI_PAINTING_LOCAL_ASR_TIMEOUT", 15.0)
    files = {
        "file": (f"voice-command{audio.extension}", audio.audio_bytes, audio.mime_type),
    }
    data = {
        "language": language,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, files=files, data=data)
    if response.status_code >= 400:
        raise AsrProviderError(f"本地 ASR 服务请求失败: HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return _extract_text_from_json(response.json())
    text = response.text.strip()
    if not text:
        raise AsrProviderError("本地 ASR 服务没有返回文本")
    return text


async def _transcribe_with_local_command(audio: AudioPayload, language: str) -> str:
    command_template = os.getenv("AI_PAINTING_LOCAL_ASR_COMMAND")
    if not command_template:
        raise AsrProviderError("未配置 AI_PAINTING_LOCAL_ASR_COMMAND")

    timeout = _read_float_env("AI_PAINTING_LOCAL_ASR_TIMEOUT", 15.0)
    with tempfile.TemporaryDirectory(prefix="ai-painting-asr-") as tmp_dir:
        audio_path = Path(tmp_dir) / f"voice-command{audio.extension}"
        audio_path.write_bytes(audio.audio_bytes)
        command = command_template.format(audio=str(audio_path), language=language, workdir=tmp_dir)
        command_args = command if os.name == "nt" else shlex.split(command)
        process = await asyncio.to_thread(
            subprocess.run,
            command_args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "本地 ASR 命令执行失败"
        raise AsrProviderError(message)
    text = process.stdout.strip()
    if not text:
        raise AsrProviderError("本地 ASR 命令没有输出文本")
    return text


async def _transcribe_with_local(audio: AudioPayload, language: str) -> str:
    if os.getenv("AI_PAINTING_LOCAL_ASR_URL"):
        return await _transcribe_with_local_url(audio, language)
    return await _transcribe_with_local_command(audio, language)


async def transcribe_audio_data_url(audio_data_url: str, language: str = "zh") -> AsrTranscriptionResponse:
    request_started_at = perf_counter()
    normalized_language = normalize_asr_language(language)
    audio = parse_audio_data_url(audio_data_url)
    attempts: list[AsrProviderAttempt] = []

    for provider in get_asr_provider_chain():
        if not is_provider_configured(provider):
            attempts.append(
                AsrProviderAttempt(provider=provider, status="skipped", message="未配置")
            )
            continue

        started_at = perf_counter()
        try:
            if provider == "xiaomi":
                text = await _transcribe_with_xiaomi(audio, normalized_language)
            elif provider == "local":
                text = await _transcribe_with_local(audio, normalized_language)
            else:
                continue
        except (AsrProviderError, httpx.HTTPError, subprocess.SubprocessError, TimeoutError) as exc:
            attempts.append(
                AsrProviderAttempt(
                    provider=provider,
                    status="failed",
                    message=str(exc),
                    latency_ms=round((perf_counter() - started_at) * 1000, 2),
                )
            )
            continue

        attempts.append(
            AsrProviderAttempt(
                provider=provider,
                status="success",
                message="识别成功",
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
        )
        return AsrTranscriptionResponse(
            text=text,
            provider=provider,
            provider_label=provider_label(provider),
            attempts=attempts,
            metrics=AsrTranscriptionMetrics(
                total_ms=round((perf_counter() - request_started_at) * 1000, 2),
                audio_bytes=len(audio.audio_bytes),
                attempt_count=len(attempts),
                successful_provider=provider,
                fallback_count=max(0, len(attempts) - 1),
            ),
        )

    raise AsrProvidersUnavailable(attempts)
