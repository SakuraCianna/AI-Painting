from __future__ import annotations

import re
from typing import Any

from .schemas import CommandPlan, OperationRequest


COLOR_MAP: dict[str, str] = {
    "红色": "#dc2626",
    "蓝色": "#2563eb",
    "浅蓝色": "#7dd3fc",
    "绿色": "#16a34a",
    "黄色": "#facc15",
    "黑色": "#111827",
    "白色": "#ffffff",
    "米白色": "#faf7ed",
    "灰色": "#6b7280",
    "透明": "transparent",
}

SHAPE_MAP: dict[str, str] = {
    "圆形": "circle",
    "圆": "circle",
    "矩形": "rect",
    "方形": "rect",
    "正方形": "rect",
    "椭圆": "ellipse",
    "三角形": "triangle",
    "线条": "line",
    "直线": "line",
    "线": "line",
    "箭头": "arrow",
    "星星": "star",
    "星形": "star",
    "文字": "text",
    "文本": "text",
}

CHINESE_DIGITS: dict[str, int] = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def chinese_number_to_int(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in CHINESE_DIGITS:
        return CHINESE_DIGITS[text]
    if text == "十":
        return 10
    if "百" in text:
        left, _, right = text.partition("百")
        hundreds = CHINESE_DIGITS.get(left, 1 if left == "" else 0)
        return hundreds * 100 + (chinese_number_to_int(right) or 0)
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CHINESE_DIGITS.get(left, 1 if left == "" else 0)
        return tens * 10 + (chinese_number_to_int(right) or 0)
    return None


def normalize_text(text: str) -> str:
    normalized = text.strip().lower()
    replacements = {
        "退回一步": "撤销",
        "取消上一步": "撤销",
        "返回上一步": "撤销",
        "重做": "恢复",
        "重新执行": "恢复",
        "存一下": "保存",
        "另存": "保存",
        "导出图片": "导出 png",
        "导出为png": "导出 png",
        "导出为 png": "导出 png",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _find_color(text: str, default: str = "#2563eb") -> str:
    # 先匹配长颜色名, 避免“浅蓝色”被“蓝色”提前命中。
    for name in sorted(COLOR_MAP, key=len, reverse=True):
        if name in text:
            return COLOR_MAP[name]
    return default


def _find_shape(text: str) -> str | None:
    for name in sorted(SHAPE_MAP, key=len, reverse=True):
        if name in text:
            return SHAPE_MAP[name]
    return None


def _extract_number(text: str, after: str, default: int) -> int:
    pattern = rf"{after}\s*([0-9]+|[零一二两三四五六七八九十百]+)"
    match = re.search(pattern, text)
    if not match:
        return default
    return chinese_number_to_int(match.group(1)) or default


def _base_style(text: str) -> dict[str, Any]:
    color = _find_color(text)
    stroke = "#111827" if color == "transparent" else color
    return {"fill": color, "stroke": stroke, "strokeWidth": 2, "opacity": 1}


def _position(text: str) -> tuple[int, int]:
    if "左上" in text:
        return 160, 140
    if "右上" in text:
        return 864, 140
    if "左下" in text:
        return 160, 628
    if "右下" in text:
        return 864, 628
    if "左边" in text or "左侧" in text:
        return 256, 384
    if "右边" in text or "右侧" in text:
        return 768, 384
    if "顶部" in text or "上方" in text:
        return 512, 160
    if "底部" in text or "下方" in text:
        return 512, 608
    return 512, 384


def _make_object(text: str, shape: str) -> dict[str, Any]:
    x, y = _position(text)
    style = _base_style(text)
    if shape == "circle":
        radius = _extract_number(text, "半径", 80)
        return {"type": "circle", "name": "圆形", "geometry": {"cx": x, "cy": y, "radius": radius}, "style": style}
    if shape == "rect":
        width = _extract_number(text, "宽", 220)
        height = _extract_number(text, "高", 140)
        return {
            "type": "rect",
            "name": "矩形",
            "geometry": {"x": x - width // 2, "y": y - height // 2, "width": width, "height": height, "radius": 8},
            "style": style,
        }
    if shape == "ellipse":
        return {"type": "ellipse", "name": "椭圆", "geometry": {"cx": x, "cy": y, "rx": 140, "ry": 80}, "style": style}
    if shape == "triangle":
        return {"type": "triangle", "name": "三角形", "geometry": {"x": x, "y": y, "size": 180}, "style": style}
    if shape in {"line", "arrow"}:
        return {
            "type": shape,
            "name": "箭头" if shape == "arrow" else "线条",
            "geometry": {"x1": x - 120, "y1": y + 80, "x2": x + 120, "y2": y - 80},
            "style": {**style, "fill": "transparent", "strokeWidth": 4},
        }
    if shape == "star":
        return {"type": "star", "name": "星星", "geometry": {"cx": x, "cy": y, "outerRadius": 80, "innerRadius": 36, "points": 5}, "style": style}
    content_match = re.search(r"(?:写|内容是|文字是|文本是)(.+)$", text)
    content = content_match.group(1).strip() if content_match else "语音文字"
    return {
        "type": "text",
        "name": "文字",
        "geometry": {"x": x, "y": y, "fontSize": 48, "content": content},
        "style": {**style, "fill": style["fill"], "stroke": "transparent"},
    }


def _house_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    operations = [
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": "房子主体",
                    "geometry": {"x": 350, "y": 330, "width": 320, "height": 240, "radius": 6},
                    "style": {"fill": "#faf7ed", "stroke": "#111827", "strokeWidth": 3, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "triangle",
                    "name": "红色屋顶",
                    "geometry": {"x": 510, "y": 270, "size": 380},
                    "style": {"fill": "#dc2626", "stroke": "#111827", "strokeWidth": 3, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": "蓝色门",
                    "geometry": {"x": 475, "y": 440, "width": 70, "height": 130, "radius": 4},
                    "style": {"fill": "#2563eb", "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": "窗户1",
                    "geometry": {"x": 390, "y": 380, "width": 64, "height": 64, "radius": 4},
                    "style": {"fill": "#7dd3fc", "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": "窗户2",
                    "geometry": {"x": 570, "y": 380, "width": 64, "height": 64, "radius": 4},
                    "style": {"fill": "#7dd3fc", "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
                }
            },
        ),
    ]
    return CommandPlan(raw_text=raw_text, normalized_text=normalized_text, operations=operations, confidence=0.9)


def parse_command(text: str) -> CommandPlan:
    normalized = normalize_text(text)
    operations: list[OperationRequest] = []
    requires_confirmation = False
    risk_level = "low"

    if "清空" in normalized:
        return CommandPlan(
            raw_text=text,
            normalized_text=normalized,
            operations=[OperationRequest(operation_type="clear_canvas", payload={})],
            confidence=0.8,
            requires_confirmation=True,
            clarification_question="清空画布会删除当前所有对象, 请说确认清空或取消",
            risk_level="high",
        )

    if "撤销" in normalized:
        operations.append(OperationRequest(operation_type="undo", payload={}))
    elif "恢复" in normalized:
        operations.append(OperationRequest(operation_type="redo", payload={}))
    elif "保存" in normalized:
        title_match = re.search(r"(?:名字叫|命名为|叫)([\u4e00-\u9fa5a-zA-Z0-9_-]+)", normalized)
        operations.append(OperationRequest(operation_type="save_artwork", payload={"title": title_match.group(1) if title_match else None}))
    elif "导出 png" in normalized or "导出png" in normalized:
        operations.append(OperationRequest(operation_type="export_artwork", payload={"format": "png"}))
    elif "新建" in normalized and "画布" in normalized:
        width, height = (1280, 720) if "横向" in normalized else (720, 1280) if "竖向" in normalized else (1024, 768)
        operations.append(
            OperationRequest(
                operation_type="create_canvas",
                payload={"width": width, "height": height, "background": _find_color(normalized, "#ffffff")},
            )
        )
    elif "房子" in normalized:
        return _house_plan(text, normalized)
    elif any(keyword in normalized for keyword in ("改成", "换成", "加粗")):
        style: dict[str, Any] = {}
        if any(color in normalized for color in COLOR_MAP):
            style["fill"] = _find_color(normalized)
        if "加粗" in normalized:
            style["strokeWidth"] = 5
        operations.append(OperationRequest(operation_type="set_style", payload={"target": {"selector": "latest"}, "style": style}))
    elif "移动" in normalized or "往" in normalized or "向" in normalized:
        amount = _extract_number(normalized, "(?:移动|一点|像素|右|左|上|下)", 20)
        dx = amount if "右" in normalized else -amount if "左" in normalized else 0
        dy = amount if "下" in normalized else -amount if "上" in normalized else 0
        operations.append(OperationRequest(operation_type="move_object", payload={"target": {"selector": "latest"}, "dx": dx, "dy": dy}))
    else:
        shape = _find_shape(normalized)
        if shape:
            operations.append(OperationRequest(operation_type="add_object", payload={"object": _make_object(normalized, shape)}))

    if not operations:
        return CommandPlan(
            raw_text=text,
            normalized_text=normalized,
            operations=[],
            confidence=0.35,
            requires_confirmation=True,
            clarification_question="我还没有听懂这条绘图指令, 可以换一种说法吗?",
            risk_level="medium",
        )

    return CommandPlan(
        raw_text=text,
        normalized_text=normalized,
        operations=operations,
        confidence=0.86,
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
    )
