from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app import image_generation
from app.image_generation import ImageGenerationError, generate_image_object, polish_image_object


SAMPLE_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_image_edit_uses_official_openai_fallback_after_proxy_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_post(
        endpoint: str,
        api_key: str,
        fields: dict[str, Any],
        files: dict[str, tuple[str, bytes, str]],
        timeout: float,
        provider_name: str,
    ) -> tuple[str, str]:
        calls.append(
            {
                "endpoint": endpoint,
                "api_key": api_key,
                "fields": fields,
                "files": files,
                "timeout": timeout,
                "provider_name": provider_name,
            }
        )
        if len(calls) == 1:
            raise ImageGenerationError("图生图精修请求失败: HTTP 502")
        return "data:image/png;base64,ZmFrZQ==", provider_name

    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_BASE_URL", "https://corenode.best/v1")
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_API_KEY", "proxy-key")
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_MODEL", "gpt-image-2")
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_SIZE", "1024x768")
    monkeypatch.setenv("OPENAI_API_KEY", "official-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.example/v1")
    monkeypatch.delenv("AI_PAINTING_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_PAINTING_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_PAINTING_OPENAI_IMAGE_SIZE", raising=False)
    monkeypatch.setattr(image_generation, "_post_image_edit_multipart", fake_post)

    image_object = asyncio.run(polish_image_object({"input_image_data_url": SAMPLE_PNG_DATA_URL}, fallback_width=1024, fallback_height=768))

    assert image_object["geometry"]["provider"] == "openai_official"
    assert [call["endpoint"] for call in calls] == [
        "https://corenode.best/v1/images/edits",
        "https://api.openai.example/v1/images/edits",
    ]
    assert calls[0]["api_key"] == "proxy-key"
    assert calls[1]["api_key"] == "official-key"
    assert set(calls[0]["files"]) == {"image"}
    assert set(calls[1]["files"]) == {"image[]"}
    assert calls[0]["fields"]["size"] == "1024x768"
    assert calls[1]["fields"]["size"] == "auto"


def test_text_image_uses_official_openai_fallback_after_proxy_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_post(
        endpoint: str,
        api_key: str,
        body: dict[str, Any],
        timeout: float,
        provider_name: str,
    ) -> tuple[str, str]:
        calls.append({"endpoint": endpoint, "api_key": api_key, "body": body, "timeout": timeout, "provider_name": provider_name})
        if len(calls) == 1:
            raise ImageGenerationError("文字转图片请求失败: HTTP 502")
        return "data:image/png;base64,ZmFrZQ==", provider_name

    monkeypatch.setenv("AI_PAINTING_IMAGE_PROVIDER", "openai_compatible")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_BASE_URL", "https://corenode.best/v1")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_API_KEY", "proxy-key")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_MODEL", "gpt-image-2")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_SIZE", "1024x768")
    monkeypatch.setenv("OPENAI_API_KEY", "official-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.example/v1")
    monkeypatch.delenv("AI_PAINTING_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_PAINTING_OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("AI_PAINTING_OPENAI_IMAGE_SIZE", "1024x1024")
    monkeypatch.setattr(image_generation, "_post_image_generation_json", fake_post)

    image_object = asyncio.run(generate_image_object({"prompt": "一张产品海报", "width": 1024, "height": 768}))

    assert image_object["geometry"]["provider"] == "openai_official"
    assert [call["endpoint"] for call in calls] == [
        "https://corenode.best/v1/images/generations",
        "https://api.openai.example/v1/images/generations",
    ]
    assert calls[0]["api_key"] == "proxy-key"
    assert calls[1]["api_key"] == "official-key"
    assert calls[0]["body"]["size"] == "1024x768"
    assert calls[1]["body"]["size"] == "1024x1024"
