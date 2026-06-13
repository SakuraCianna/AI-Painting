from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app import image_generation
from app.image_generation import (
    ImageGenerationError,
    _decode_image_data_url,
    _extract_image_source,
    _generate_with_http,
    _post_image_edit_multipart,
    _post_image_generation_json,
    generate_image_object,
    polish_image_object,
)


SAMPLE_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class _FakeImageResponse:
    def __init__(
        self,
        status_code: int,
        *,
        json_body: dict[str, Any] | Exception | None = None,
        content: bytes = b"",
        content_type: str = "application/json",
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.content = content
        self.headers = {"content-type": content_type}

    def json(self) -> dict[str, Any]:
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body or {}


def test_placeholder_image_object_bounds_dimensions_and_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PAINTING_IMAGE_PROVIDER", "placeholder")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_HEIGHT", "not-a-number")

    image_object = asyncio.run(
        generate_image_object(
            {
                "prompt": "一张测试海报",
                "width": 9999,
                "height": "bad",
                "semantic_tags": ["poster", "poster"],
                "opacity": "0.6",
            }
        )
    )

    assert image_object["type"] == "image"
    assert image_object["geometry"]["width"] == 2048
    assert image_object["geometry"]["height"] == 512
    assert image_object["geometry"]["src"].startswith("data:image/svg+xml;base64,")
    assert image_object["style"]["opacity"] == 0.6
    assert image_object["semantic_tags"] == ["generated.image", "image", "poster"]


def test_image_providers_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PAINTING_IMAGE_PROVIDER", "disabled")
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_PROVIDER", "off")

    with pytest.raises(ImageGenerationError, match="Provider 未启用"):
        asyncio.run(generate_image_object({"prompt": "一张图"}))
    with pytest.raises(ImageGenerationError, match="Provider 未启用"):
        asyncio.run(polish_image_object({"input_image_data_url": SAMPLE_PNG_DATA_URL}, fallback_width=512, fallback_height=512))


def test_extract_image_source_accepts_common_provider_shapes() -> None:
    assert _extract_image_source({"image_data_url": "data:image/png;base64,AAA"}) == "data:image/png;base64,AAA"
    assert _extract_image_source({"data": [{"b64_json": "QUJD"}]}) == "data:image/png;base64,QUJD"
    assert _extract_image_source({"images": ["https://example.test/image.png"]}) == "https://example.test/image.png"
    assert _extract_image_source({"images": [{"url": "https://example.test/nested.png"}]}) == "https://example.test/nested.png"
    assert _extract_image_source({"data": []}) is None


def test_decode_image_data_url_validates_type_and_base64() -> None:
    mime, image_bytes = _decode_image_data_url(SAMPLE_PNG_DATA_URL)

    assert mime == "image/png"
    assert image_bytes

    with pytest.raises(ImageGenerationError, match="data URL"):
        _decode_image_data_url("https://example.test/image.png")
    with pytest.raises(ImageGenerationError, match="PNG, JPEG 或 WebP"):
        _decode_image_data_url("data:image/svg+xml;base64,AAAA")
    with pytest.raises(ImageGenerationError, match="base64"):
        _decode_image_data_url("data:image/png;base64,***")


def test_http_text_to_image_accepts_binary_and_json_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeImageResponse(200, content=b"PNG", content_type="image/png"),
        _FakeImageResponse(200, json_body={"data": [{"b64_json": "QUJD"}]}),
    ]
    calls: list[dict[str, Any]] = []

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

    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_URL", "https://image.example/generate")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_API_KEY", "image-key")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_MODEL", "demo-model")
    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_TIMEOUT", "9")
    monkeypatch.setattr("app.image_generation.httpx.AsyncClient", FakeAsyncClient)

    binary_src, binary_provider = asyncio.run(_generate_with_http("海报", 512, 384, "扁平"))
    json_src, json_provider = asyncio.run(_generate_with_http("海报", 512, 384, None))

    assert binary_src == "data:image/png;base64,UE5H"
    assert json_src == "data:image/png;base64,QUJD"
    assert binary_provider == json_provider == "http"
    assert calls[0]["headers"]["Authorization"] == "Bearer image-key"
    assert calls[0]["json"]["model"] == "demo-model"
    assert "style" not in calls[1]["json"]


def test_http_text_to_image_reports_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeImageResponse(500, json_body={"error": "server"}),
        _FakeImageResponse(200, json_body=ValueError("bad json")),
        _FakeImageResponse(200, json_body={"data": []}),
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

    monkeypatch.setenv("AI_PAINTING_TEXT_IMAGE_URL", "https://image.example/generate")
    monkeypatch.setattr("app.image_generation.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(ImageGenerationError, match="HTTP 500"):
        asyncio.run(_generate_with_http("海报", 512, 384, None))
    with pytest.raises(ImageGenerationError, match="不是图片或 JSON"):
        asyncio.run(_generate_with_http("海报", 512, 384, None))
    with pytest.raises(ImageGenerationError, match="缺少图片地址"):
        asyncio.run(_generate_with_http("海报", 512, 384, None))


def test_openai_compatible_posts_parse_json_binary_and_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeImageResponse(200, json_body={"b64_json": "QUJD"}),
        _FakeImageResponse(200, content=b"WEBP", content_type="image/webp"),
        _FakeImageResponse(200, json_body={"data": [{"url": "https://example.test/edit.png"}]}),
    ]

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, endpoint: str, *, headers, json=None, data=None, files=None):
            return responses.pop(0)

    monkeypatch.setattr("app.image_generation.httpx.AsyncClient", FakeAsyncClient)

    json_src, json_provider = asyncio.run(_post_image_generation_json("https://proxy/images", "key", {"prompt": "图"}, 30, "proxy"))
    binary_src, binary_provider = asyncio.run(_post_image_generation_json("https://proxy/images", "key", {"prompt": "图"}, 30, "proxy"))
    edit_src, edit_provider = asyncio.run(
        _post_image_edit_multipart(
            "https://proxy/edits",
            "key",
            {"prompt": "精修"},
            {"image": ("canvas.png", b"PNG", "image/png")},
            30,
            "proxy-edit",
        )
    )

    assert json_src == "data:image/png;base64,QUJD"
    assert binary_src == "data:image/webp;base64,V0VCUA=="
    assert edit_src == "https://example.test/edit.png"
    assert (json_provider, binary_provider, edit_provider) == ("proxy", "proxy", "proxy-edit")


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


def test_polish_image_object_persists_subject_region_adjustment_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PAINTING_IMAGE_EDIT_PROVIDER", "placeholder")

    image_object = asyncio.run(
        polish_image_object(
            {
                "input_image_data_url": SAMPLE_PNG_DATA_URL,
                "prompt": "精修右边人物的眼睛",
                "source_prompt": "双人肖像",
                "source_object_id": "source-1",
                "source_object_name": "双人肖像图",
                "target_subject": "右边的人",
                "target_region": "眼睛",
                "adjustment": "调亮",
            },
            fallback_width=1024,
            fallback_height=768,
        )
    )

    assert image_object["geometry"]["target_subject"] == "右边的人"
    assert image_object["geometry"]["target_region"] == "眼睛"
    assert image_object["geometry"]["adjustment"] == "调亮"
    assert image_object["geometry"]["source_prompt"] == "双人肖像"
    assert "polished.region" in image_object["semantic_tags"]
    assert "polished.subject" in image_object["semantic_tags"]


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
