from __future__ import annotations

import base64
import html
import os
import re
from typing import Any

import httpx


class ImageGenerationError(RuntimeError):
    pass


DATA_URL_PATTERN = re.compile(r"^data:(?P<mime>[-\w.+/]+);base64,(?P<data>.+)$", re.DOTALL)
OPENAI_OFFICIAL_BASE_URL = "https://api.openai.com/v1"
OFFICIAL_IMAGE_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bounded_dimension(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(128, min(parsed, 2048))


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_openai_api_key() -> str | None:
    return os.getenv("AI_PAINTING_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")


def _get_openai_base_url() -> str:
    return (os.getenv("AI_PAINTING_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or OPENAI_OFFICIAL_BASE_URL).rstrip("/")


def _official_image_size(default: str = "auto") -> str:
    configured = os.getenv("AI_PAINTING_OPENAI_IMAGE_SIZE", default).strip()
    return configured if configured in OFFICIAL_IMAGE_SIZES else "auto"


def _svg_placeholder_data_url(prompt: str, width: int, height: int) -> str:
    safe_prompt = html.escape(prompt[:140])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#e8f0fe"/>
      <stop offset="0.55" stop-color="#f8fafc"/>
      <stop offset="1" stop-color="#dcfce7"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" rx="24" fill="url(#bg)"/>
  <rect x="32" y="32" width="{width - 64}" height="{height - 64}" rx="18" fill="rgba(255,255,255,0.72)" stroke="#cbd5e1"/>
  <text x="50%" y="42%" text-anchor="middle" font-family="Arial, 'Microsoft YaHei', sans-serif" font-size="34" font-weight="700" fill="#0f172a">AI Painting</text>
  <text x="50%" y="54%" text-anchor="middle" font-family="Arial, 'Microsoft YaHei', sans-serif" font-size="20" fill="#334155">{safe_prompt}</text>
  <text x="50%" y="65%" text-anchor="middle" font-family="Arial, 'Microsoft YaHei', sans-serif" font-size="16" fill="#64748b">Text-to-image provider placeholder</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _extract_image_source(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return _extract_image_source(first)
    for key in ("image_data_url", "data_url", "url", "image_url"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    b64_json = payload.get("b64_json")
    if isinstance(b64_json, str) and b64_json.strip():
        return f"data:image/png;base64,{b64_json.strip()}"
    images = payload.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return _extract_image_source(first)
        if isinstance(first, str):
            return first
    return None


def _decode_image_data_url(data_url: str) -> tuple[str, bytes]:
    match = DATA_URL_PATTERN.match(data_url.strip())
    if not match:
        raise ImageGenerationError("画布图片必须是 base64 data URL")
    mime = match.group("mime")
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise ImageGenerationError("画布图片只支持 PNG, JPEG 或 WebP")
    try:
        return mime, base64.b64decode(match.group("data"), validate=True)
    except ValueError as exc:
        raise ImageGenerationError("画布图片 base64 无法解析") from exc


async def _generate_with_http(prompt: str, width: int, height: int, style: str | None) -> tuple[str, str]:
    url = os.getenv("AI_PAINTING_TEXT_IMAGE_URL")
    if not url:
        raise ImageGenerationError("未配置 AI_PAINTING_TEXT_IMAGE_URL")
    timeout = float(os.getenv("AI_PAINTING_TEXT_IMAGE_TIMEOUT", "60"))
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("AI_PAINTING_TEXT_IMAGE_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["api-key"] = api_key
    body = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "style": style,
        "model": os.getenv("AI_PAINTING_TEXT_IMAGE_MODEL"),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json={key: value for key, value in body.items() if value is not None})
    if response.status_code >= 400:
        raise ImageGenerationError(f"文字转图片请求失败: HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        encoded = base64.b64encode(response.content).decode("ascii")
        return f"data:{content_type.split(';')[0]};base64,{encoded}", "http"
    try:
        image_source = _extract_image_source(response.json())
    except ValueError as exc:
        raise ImageGenerationError("文字转图片响应不是图片或 JSON") from exc
    if not image_source:
        raise ImageGenerationError("文字转图片响应缺少图片地址")
    return image_source, "http"


async def _post_image_generation_json(
    endpoint: str,
    api_key: str,
    body: dict[str, Any],
    timeout: float,
    provider_name: str,
) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, headers=headers, json={key: value for key, value in body.items() if value is not None})
    if response.status_code >= 400:
        raise ImageGenerationError(f"文字转图片请求失败: HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        encoded = base64.b64encode(response.content).decode("ascii")
        return f"data:{content_type.split(';')[0]};base64,{encoded}", provider_name
    try:
        image_source = _extract_image_source(response.json())
    except ValueError as exc:
        raise ImageGenerationError("文字转图片响应不是图片或 JSON") from exc
    if not image_source:
        raise ImageGenerationError("文字转图片响应缺少图片地址")
    return image_source, provider_name


async def _generate_with_openai_compatible(prompt: str, width: int, height: int, style: str | None) -> tuple[str, str]:
    base_url = os.getenv("AI_PAINTING_TEXT_IMAGE_BASE_URL", os.getenv("AI_PAINTING_IMAGE_EDIT_BASE_URL", "")).rstrip("/")
    api_key = os.getenv("AI_PAINTING_TEXT_IMAGE_API_KEY") or os.getenv("AI_PAINTING_IMAGE_EDIT_API_KEY")
    if not base_url:
        raise ImageGenerationError("未配置 AI_PAINTING_TEXT_IMAGE_BASE_URL")
    if not api_key:
        raise ImageGenerationError("未配置 AI_PAINTING_TEXT_IMAGE_API_KEY")
    endpoint = os.getenv("AI_PAINTING_TEXT_IMAGE_ENDPOINT") or f"{base_url}/images/generations"
    timeout = _read_float_env("AI_PAINTING_TEXT_IMAGE_TIMEOUT", 120.0)
    body = {
        "model": os.getenv("AI_PAINTING_TEXT_IMAGE_MODEL", os.getenv("AI_PAINTING_IMAGE_EDIT_MODEL", "gpt-image-2")),
        "prompt": prompt,
        "size": os.getenv("AI_PAINTING_TEXT_IMAGE_SIZE") or f"{width}x{height}",
        "style": style,
        "response_format": os.getenv("AI_PAINTING_TEXT_IMAGE_RESPONSE_FORMAT", "b64_json"),
    }
    try:
        return await _post_image_generation_json(endpoint, api_key, body, timeout, "openai_compatible")
    except ImageGenerationError as primary_error:
        openai_key = _get_openai_api_key()
        if not openai_key:
            raise primary_error
        official_base_url = _get_openai_base_url()
        official_endpoint = f"{official_base_url}/images/generations"
        official_body = {
            "model": os.getenv("AI_PAINTING_OPENAI_IMAGE_MODEL", body["model"]),
            "prompt": prompt,
            "size": _official_image_size(),
            "quality": os.getenv("AI_PAINTING_OPENAI_IMAGE_QUALITY", "auto"),
            "background": os.getenv("AI_PAINTING_OPENAI_IMAGE_BACKGROUND", "auto"),
            "output_format": os.getenv("AI_PAINTING_OPENAI_IMAGE_OUTPUT_FORMAT", "png"),
        }
        try:
            src, _ = await _post_image_generation_json(official_endpoint, openai_key, official_body, timeout, "openai_official")
            return src, "openai_official"
        except ImageGenerationError as fallback_error:
            raise ImageGenerationError(f"{primary_error}; OpenAI 官方备用失败: {fallback_error}") from fallback_error


async def _post_image_edit_multipart(
    endpoint: str,
    api_key: str,
    fields: dict[str, Any],
    files: dict[str, tuple[str, bytes, str]],
    timeout: float,
    provider_name: str,
) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, headers=headers, data={key: value for key, value in fields.items() if value is not None}, files=files)
    if response.status_code >= 400:
        raise ImageGenerationError(f"图生图精修请求失败: HTTP {response.status_code}")
    try:
        image_source = _extract_image_source(response.json())
    except ValueError as exc:
        raise ImageGenerationError("图生图精修响应不是 JSON") from exc
    if not image_source:
        raise ImageGenerationError("图生图精修响应缺少图片地址")
    return image_source, provider_name


async def _edit_with_openai_compatible(prompt: str, image_data_url: str, width: int, height: int) -> tuple[str, str]:
    base_url = os.getenv("AI_PAINTING_IMAGE_EDIT_BASE_URL", "").rstrip("/")
    api_key = os.getenv("AI_PAINTING_IMAGE_EDIT_API_KEY")
    if not base_url:
        raise ImageGenerationError("未配置 AI_PAINTING_IMAGE_EDIT_BASE_URL")
    if not api_key:
        raise ImageGenerationError("未配置 AI_PAINTING_IMAGE_EDIT_API_KEY")
    mime, image_bytes = _decode_image_data_url(image_data_url)
    endpoint = os.getenv("AI_PAINTING_IMAGE_EDIT_ENDPOINT") or f"{base_url}/images/edits"
    model = os.getenv("AI_PAINTING_IMAGE_EDIT_MODEL", "gpt-image-2")
    timeout = _read_float_env("AI_PAINTING_IMAGE_EDIT_TIMEOUT", 120.0)
    size = os.getenv("AI_PAINTING_IMAGE_EDIT_SIZE") or f"{width}x{height}"
    response_format = os.getenv("AI_PAINTING_IMAGE_EDIT_RESPONSE_FORMAT", "b64_json")
    fields = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": response_format,
    }
    files = {
        "image": ("canvas.png", image_bytes, mime),
    }
    try:
        return await _post_image_edit_multipart(endpoint, api_key, fields, files, timeout, "openai_compatible")
    except ImageGenerationError as primary_error:
        openai_key = _get_openai_api_key()
        if not openai_key:
            raise primary_error
        official_base_url = _get_openai_base_url()
        official_endpoint = f"{official_base_url}/images/edits"
        official_fields = {
            "model": os.getenv("AI_PAINTING_OPENAI_IMAGE_MODEL", model),
            "prompt": prompt,
            "size": _official_image_size(),
            "quality": os.getenv("AI_PAINTING_OPENAI_IMAGE_QUALITY", "auto"),
            "background": os.getenv("AI_PAINTING_OPENAI_IMAGE_BACKGROUND", "auto"),
            "output_format": os.getenv("AI_PAINTING_OPENAI_IMAGE_OUTPUT_FORMAT", "png"),
        }
        official_files = {
            "image[]": ("canvas.png", image_bytes, mime),
        }
        try:
            return await _post_image_edit_multipart(official_endpoint, openai_key, official_fields, official_files, timeout, "openai_official")
        except ImageGenerationError as fallback_error:
            raise ImageGenerationError(f"{primary_error}; OpenAI 官方备用失败: {fallback_error}") from fallback_error


async def generate_image_object(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or payload.get("text") or "").strip()
    if not prompt:
        raise ImageGenerationError("生成图片需要提示词")
    width = _bounded_dimension(payload.get("width"), _read_int_env("AI_PAINTING_TEXT_IMAGE_WIDTH", 512))
    height = _bounded_dimension(payload.get("height"), _read_int_env("AI_PAINTING_TEXT_IMAGE_HEIGHT", 512))
    provider = os.getenv("AI_PAINTING_IMAGE_PROVIDER", "placeholder").strip().lower()
    if provider in {"disabled", "none", "off"}:
        raise ImageGenerationError("文字转图片 Provider 未启用")
    if provider == "http":
        src, provider_name = await _generate_with_http(prompt, width, height, payload.get("style"))
    elif provider in {"openai", "openai_compatible", "gpt_image"}:
        src, provider_name = await _generate_with_openai_compatible(prompt, width, height, payload.get("style"))
    else:
        src = _svg_placeholder_data_url(prompt, width, height)
        provider_name = "placeholder"
    semantic_tags = payload.get("semantic_tags")
    if not isinstance(semantic_tags, list):
        semantic_tags = []
    return {
        "type": "image",
        "name": str(payload.get("name") or "生成图片"),
        "layer_id": str(payload.get("layer_id") or "middle"),
        "group_id": payload.get("group_id"),
        "semantic_tags": sorted({"generated.image", "image", *[str(tag) for tag in semantic_tags]}),
        "geometry": {
            "x": int(payload.get("x", 256)),
            "y": int(payload.get("y", 128)),
            "width": width,
            "height": height,
            "src": src,
            "prompt": prompt,
            "provider": provider_name,
            "preserveAspectRatio": payload.get("preserveAspectRatio", "xMidYMid slice"),
        },
        "style": {"opacity": float(payload.get("opacity", 1))},
    }


async def polish_image_object(payload: dict[str, Any], *, fallback_width: int, fallback_height: int) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "精修当前画布, 保留主要构图和对象关系, 丰富细节, 提升整体质感").strip()
    image_data_url = str(payload.get("input_image_data_url") or "").strip()
    if not image_data_url:
        raise ImageGenerationError("精修当前图片需要前端提供画布截图")
    width = _bounded_dimension(payload.get("width"), fallback_width)
    height = _bounded_dimension(payload.get("height"), fallback_height)
    provider = os.getenv("AI_PAINTING_IMAGE_EDIT_PROVIDER", "placeholder").strip().lower()
    if provider in {"openai", "openai_compatible", "gpt_image"}:
        src, provider_name = await _edit_with_openai_compatible(prompt, image_data_url, width, height)
    elif provider in {"disabled", "none", "off"}:
        raise ImageGenerationError("图生图精修 Provider 未启用")
    else:
        src = _svg_placeholder_data_url(f"精修预览: {prompt}", width, height)
        provider_name = "placeholder"
    semantic_tags = ["generated.image", "image", "polished.image"]
    target_region = str(payload.get("target_region") or "").strip()
    target_subject = str(payload.get("target_subject") or "").strip()
    if target_region:
        semantic_tags.append("polished.region")
    if target_subject:
        semantic_tags.append("polished.subject")
    geometry = {
        "x": int(payload.get("x", 0)),
        "y": int(payload.get("y", 0)),
        "width": width,
        "height": height,
        "src": src,
        "prompt": prompt,
        "provider": provider_name,
        "preserveAspectRatio": payload.get("preserveAspectRatio", "xMidYMid slice"),
    }
    for key in ("source_prompt", "source_object_id", "source_object_name", "target_region", "target_subject", "adjustment"):
        value = payload.get(key)
        if value:
            geometry[key] = str(value)
    return {
        "type": "image",
        "name": str(payload.get("name") or "精修版本"),
        "layer_id": str(payload.get("layer_id") or "foreground"),
        "group_id": payload.get("group_id"),
        "semantic_tags": semantic_tags,
        "geometry": geometry,
        "style": {"opacity": float(payload.get("opacity", 1))},
    }
