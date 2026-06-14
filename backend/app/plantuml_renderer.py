from __future__ import annotations

import base64
import os
import re
import subprocess
import zlib
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path

import httpx


PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
BLOCKED_DIRECTIVE_PATTERN = re.compile(r"^\s*!(?:include|includeurl|includesub|import)\b", re.IGNORECASE | re.MULTILINE)
START_TO_END_MARKERS = {
    "@startuml": "@enduml",
    "@startwbs": "@endwbs",
    "@startgantt": "@endgantt",
}
START_MARKER_PATTERN = re.compile(r"^\s*@(startuml|startwbs|startgantt)\b", re.IGNORECASE | re.MULTILINE)
END_MARKER_PATTERN = re.compile(r"^\s*@(enduml|endwbs|endgantt)\b", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class PlantUMLRenderResult:
    svg: str
    data_url: str
    mode: str
    error: str | None = None


class PlantUMLRenderError(ValueError):
    pass


def render_plantuml_source(source: str) -> PlantUMLRenderResult:
    clean_source = validate_plantuml_source(source)
    return _render_plantuml_cached(
        clean_source,
        os.getenv("AI_PAINTING_PLANTUML_JAR", "").strip(),
        os.getenv("AI_PAINTING_PLANTUML_SERVER_URL", "").strip(),
        os.getenv("AI_PAINTING_PLANTUML_SECURITY_PROFILE", "SANDBOX").strip() or "SANDBOX",
        os.getenv("AI_PAINTING_JAVA_BIN", "java").strip() or "java",
        _read_timeout_seconds(),
    )


def validate_plantuml_source(source: str) -> str:
    clean_source = source.strip()
    max_chars = _read_int_env("AI_PAINTING_PLANTUML_MAX_SOURCE_CHARS", 12_000)
    if len(clean_source) > max_chars:
        raise PlantUMLRenderError("PlantUML 源码过长")
    if BLOCKED_DIRECTIVE_PATTERN.search(clean_source):
        raise PlantUMLRenderError("PlantUML 源码不能使用 include 或 import 指令")
    _validate_single_plantuml_block(clean_source)
    return clean_source


def _validate_single_plantuml_block(source: str) -> None:
    lines = source.splitlines()
    if not lines:
        raise PlantUMLRenderError("PlantUML 源码不能为空")

    first_marker = lines[0].strip().split(maxsplit=1)[0].lower()
    expected_end_marker = START_TO_END_MARKERS.get(first_marker)
    if expected_end_marker is None:
        raise PlantUMLRenderError("PlantUML 源码必须以 @startuml、@startwbs 或 @startgantt 开始")

    last_marker = lines[-1].strip().split(maxsplit=1)[0].lower()
    if last_marker != expected_end_marker:
        raise PlantUMLRenderError(f"PlantUML 源码必须以对应的 {expected_end_marker} 结束")

    start_count = len(START_MARKER_PATTERN.findall(source))
    end_count = len(END_MARKER_PATTERN.findall(source))
    if start_count != 1 or end_count != 1:
        raise PlantUMLRenderError("PlantUML 源码只能包含一个完整图表块")


@lru_cache(maxsize=64)
def _render_plantuml_cached(
    source: str,
    jar_path: str,
    server_url: str,
    security_profile: str,
    java_bin: str,
    timeout_seconds: float,
) -> PlantUMLRenderResult:
    if jar_path:
        try:
            return _render_with_local_jar(source, jar_path, security_profile, java_bin, timeout_seconds)
        except PlantUMLRenderError as exc:
            return _fallback_svg(source, "fallback_local_svg", str(exc))
    if server_url:
        try:
            return _render_with_server(source, server_url, timeout_seconds)
        except PlantUMLRenderError as exc:
            return _fallback_svg(source, "fallback_local_svg", str(exc))
    return _fallback_svg(source, "fallback_local_svg", "未配置 PlantUML jar 或 server, 已显示源码预览")


def _render_with_local_jar(source: str, jar_path: str, security_profile: str, java_bin: str, timeout_seconds: float) -> PlantUMLRenderResult:
    resolved_jar = Path(jar_path).expanduser()
    if not resolved_jar.is_file():
        raise PlantUMLRenderError("PlantUML jar 文件不存在")
    env = os.environ.copy()
    env["PLANTUML_SECURITY_PROFILE"] = security_profile
    completed = subprocess.run(
        [java_bin, f"-DPLANTUML_SECURITY_PROFILE={security_profile}", "-jar", str(resolved_jar), "-tsvg", "-pipe"],
        input=source,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "PlantUML jar 渲染失败"
        raise PlantUMLRenderError(message[:400])
    svg = completed.stdout.strip()
    _ensure_svg(svg)
    return PlantUMLRenderResult(svg=svg, data_url=_svg_data_url(svg), mode="local_jar")


def _render_with_server(source: str, server_url: str, timeout_seconds: float) -> PlantUMLRenderResult:
    base_url = server_url.rstrip("/")
    encoded = _plantuml_encode(source)
    try:
        response = httpx.get(f"{base_url}/svg/{encoded}", timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PlantUMLRenderError(f"PlantUML server 渲染失败: {exc}") from exc
    svg = response.text.strip()
    _ensure_svg(svg)
    return PlantUMLRenderResult(svg=svg, data_url=_svg_data_url(svg), mode="server")


def _ensure_svg(svg: str) -> None:
    if "<svg" not in svg[:300].lower() or "</svg>" not in svg[-300:].lower():
        raise PlantUMLRenderError("PlantUML 返回内容不是 SVG")


def _fallback_svg(source: str, mode: str, error: str) -> PlantUMLRenderResult:
    lines = source.splitlines()
    preview_lines = lines[:18]
    text_rows = "\n".join(
        f'<text x="44" y="{182 + index * 28}" fill="#3c4043" font-family="Consolas, monospace" font-size="18">{escape(line)}</text>'
        for index, line in enumerate(preview_lines)
    )
    extra_count = max(len(lines) - len(preview_lines), 0)
    extra_row = (
        f'<text x="44" y="{182 + len(preview_lines) * 28}" fill="#5f6368" font-family="Consolas, monospace" font-size="16">... 省略 {extra_count} 行</text>'
        if extra_count
        else ""
    )
    safe_error = escape(error)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768" viewBox="0 0 1024 768">
<rect width="1024" height="768" fill="#ffffff"/>
<rect x="28" y="28" width="968" height="712" rx="24" fill="#f8fafc" stroke="#dadce0" stroke-width="2"/>
<text x="44" y="78" fill="#202124" font-family="Arial, sans-serif" font-size="30" font-weight="700">PlantUML 图表预览</text>
<text x="44" y="118" fill="#5f6368" font-family="Arial, sans-serif" font-size="18">{safe_error}</text>
<rect x="44" y="144" width="936" height="560" rx="14" fill="#ffffff" stroke="#e5e7eb" stroke-width="1"/>
{text_rows}
{extra_row}
</svg>"""
    return PlantUMLRenderResult(svg=svg, data_url=_svg_data_url(svg), mode=mode, error=error)


def _svg_data_url(svg: str) -> str:
    payload = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{payload}"


def _plantuml_encode(source: str) -> str:
    compressed = zlib.compress(source.encode("utf-8"))[2:-4]
    return _encode_plantuml_bytes(compressed)


def _encode_plantuml_bytes(data: bytes) -> str:
    result: list[str] = []
    for index in range(0, len(data), 3):
        chunk = data[index : index + 3]
        b1 = chunk[0]
        b2 = chunk[1] if len(chunk) > 1 else 0
        b3 = chunk[2] if len(chunk) > 2 else 0
        result.append(PLANTUML_ALPHABET[b1 >> 2])
        result.append(PLANTUML_ALPHABET[((b1 & 0x3) << 4) | (b2 >> 4)])
        result.append(PLANTUML_ALPHABET[((b2 & 0xF) << 2) | (b3 >> 6)])
        result.append(PLANTUML_ALPHABET[b3 & 0x3F])
    return "".join(result)


def _read_timeout_seconds() -> float:
    try:
        value = float(os.getenv("AI_PAINTING_PLANTUML_TIMEOUT_SECONDS", "8"))
    except ValueError:
        return 8.0
    return max(1.0, min(value, 30.0))


def _read_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1000, value)
