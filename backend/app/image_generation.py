from __future__ import annotations

import base64
import html
import os
from typing import Any

import httpx


class ImageGenerationError(RuntimeError):
    pass


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
