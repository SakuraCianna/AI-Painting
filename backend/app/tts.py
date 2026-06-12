from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from .schemas import TtsSynthesisResponse


MIMO_TTS_URL = "https://api.xiaomimimo.com/v1/chat/completions"
MIMO_TTS_MODEL = "mimo-v2-tts"


class TtsProviderError(RuntimeError):
    pass


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _extract_audio_data(payload: dict[str, Any]) -> str:
    try:
        audio = payload["choices"][0]["message"]["audio"]
        data = audio["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TtsProviderError("小米 TTS 响应中没有音频数据") from exc
    if not isinstance(data, str) or not data.strip():
        raise TtsProviderError("小米 TTS 音频数据为空")
    try:
        base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise TtsProviderError("小米 TTS 音频数据不是有效 Base64") from exc
    return data


def _format_tts_text(text: str, style: str | None) -> str:
    content = text.strip()
    if not content:
        raise ValueError("TTS 文本不能为空")
    if style:
        return f"<style>{style.strip()}</style>{content}"
    return content


def build_xiaomi_tts_payload(text: str, voice: str | None = None, style: str | None = None) -> dict[str, Any]:
    return {
        "model": os.getenv("AI_PAINTING_MIMO_TTS_MODEL", MIMO_TTS_MODEL),
        "messages": [
            {
                "role": "user",
                "content": "请用自然、简洁、清晰的中文反馈绘图执行结果。",
            },
            {
                "role": "assistant",
                "content": _format_tts_text(text, style),
            },
        ],
        "audio": {
            "format": "wav",
            "voice": voice or os.getenv("AI_PAINTING_MIMO_TTS_VOICE", "default_zh"),
        },
        "stream": False,
    }


async def synthesize_with_xiaomi(text: str, voice: str | None = None, style: str | None = None) -> TtsSynthesisResponse:
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        raise TtsProviderError("未配置 MIMO_API_KEY")

    payload = build_xiaomi_tts_payload(text=text, voice=voice, style=style or os.getenv("AI_PAINTING_MIMO_TTS_STYLE"))
    timeout = _read_float_env("AI_PAINTING_MIMO_TTS_TIMEOUT", 20.0)
    url = os.getenv("AI_PAINTING_MIMO_TTS_URL", MIMO_TTS_URL)
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise TtsProviderError("小米 TTS 请求网络失败") from exc

    if response.status_code >= 400:
        raise TtsProviderError(f"小米 TTS 请求失败: HTTP {response.status_code}")

    audio_base64 = _extract_audio_data(response.json())
    return TtsSynthesisResponse(audio_data_url=f"data:audio/wav;base64,{audio_base64}")
