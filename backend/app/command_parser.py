from __future__ import annotations

import re
import math
from typing import Any

from .schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep


COLOR_MAP: dict[str, str] = {
    "红色": "#dc2626",
    "蓝色": "#2563eb",
    "浅蓝色": "#7dd3fc",
    "绿色": "#16a34a",
    "黄色": "#facc15",
    "橙色": "#f97316",
    "棕色": "#92400e",
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
    "多边形": "polygon",
    "五边形": "polygon",
    "六边形": "polygon",
    "路径": "path",
    "曲线": "bezier",
    "贝塞尔曲线": "bezier",
    "贝塞尔": "bezier",
    "云朵": "path",
    "云": "path",
    "小路": "path",
    "道路": "path",
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

SORTED_COLOR_NAMES = sorted(COLOR_MAP, key=len, reverse=True)
SORTED_SHAPE_NAMES = sorted(SHAPE_MAP, key=len, reverse=True)
WHITESPACE_PATTERN = re.compile(r"\s+")
CONTENT_PATTERN = re.compile(r"(?:写|内容是|文字是|文本是)(.+)$")
TITLE_PATTERN = re.compile(r"(?:名字叫|命名为|叫)([\u4e00-\u9fa5a-zA-Z0-9_-]+)")
OBJECT_NAME_PATTERN = re.compile(r"(?:名字叫|命名为|叫)\s*([\u4e00-\u9fa5a-zA-Z0-9_-]{1,16})")
LAYER_MAP: dict[str, str] = {
    "背景层": "background",
    "底层": "background",
    "中景层": "middle",
    "主体层": "middle",
    "前景层": "foreground",
    "顶层": "foreground",
}
SEMANTIC_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("窗户", "house.window"),
    ("屋顶", "house.roof"),
    ("门", "house.door"),
    ("房子主体", "house.body"),
    ("房子", "house"),
    ("太阳", "sun"),
    ("云", "cloud"),
    ("树", "tree"),
    ("曲线", "curve"),
    ("贝塞尔", "curve.bezier"),
    ("路径", "path"),
    ("道路", "road"),
    ("小路", "road"),
    ("多边形", "polygon"),
    ("星星", "star"),
)
SCENE_OBJECT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("小屋", "house"),
    ("房子", "house"),
    ("树", "tree"),
    ("小路", "road"),
    ("道路", "road"),
    ("云朵", "cloud"),
    ("云", "cloud"),
    ("天空", "sky"),
    ("太阳", "sun"),
    ("夜晚", "night"),
    ("灯光", "light"),
)
SCENE_LAYOUT_HINTS = ("左边", "左侧", "右边", "右侧", "上方", "下方", "天空", "前景", "背景", "中间", "后面", "前面")
SCENE_REFINEMENT_HINTS = ("画面", "场景", "保留", "局部", "整体", "氛围", "风格", "灯光")


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
    normalized = WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized


def _find_color(text: str, default: str = "#2563eb") -> str:
    # 先匹配长颜色名, 避免“浅蓝色”被“蓝色”提前命中。
    for name in SORTED_COLOR_NAMES:
        if name in text:
            return COLOR_MAP[name]
    return default


def _find_all_colors(text: str) -> list[tuple[str, str]]:
    return [(name, COLOR_MAP[name]) for name in SORTED_COLOR_NAMES if name in text]


def _find_shape(text: str) -> str | None:
    for name in SORTED_SHAPE_NAMES:
        if name in text:
            return SHAPE_MAP[name]
    return None


def _extract_object_name(text: str) -> str | None:
    match = OBJECT_NAME_PATTERN.search(text)
    return match.group(1).strip() if match else None


def _extract_layer_id(text: str) -> str | None:
    for layer_name, layer_id in LAYER_MAP.items():
        if layer_name in text:
            return layer_id
    return None


def _semantic_tags_for_text(text: str, shape: str | None = None, object_name: str | None = None) -> list[str]:
    source = f"{text} {object_name or ''}"
    tags = {tag for keyword, tag in SEMANTIC_KEYWORDS if keyword in source}
    if shape:
        tags.add(f"shape.{shape}")
    return sorted(tags)


def _target_semantic_tag(text: str) -> str | None:
    for keyword, tag in SEMANTIC_KEYWORDS:
        if keyword in text:
            return tag
    return None


def _scene_semantic_tags(text: str) -> list[str]:
    return sorted({tag for keyword, tag in SCENE_OBJECT_KEYWORDS if keyword in text})


def _needs_scene_planner(text: str) -> bool:
    scene_tags = _scene_semantic_tags(text)
    layout_count = sum(1 for keyword in SCENE_LAYOUT_HINTS if keyword in text)
    has_quantity_constraint = re.search(r"([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:个|座|棵|朵|条|片)", text) is not None
    has_scene_refinement = any(keyword in text for keyword in SCENE_REFINEMENT_HINTS) and any(
        keyword in text for keyword in ("改成", "变成", "加", "保持", "保留", "不要")
    )
    if "场景" in text and any(keyword in text for keyword in ("画", "创建", "添加", "改成")):
        return True
    if has_scene_refinement and ("画面" in text or len(scene_tags) >= 2):
        return True
    if layout_count >= 2 and len(scene_tags) >= 3:
        return True
    return bool(has_quantity_constraint and len(scene_tags) >= 3 and any(keyword in text for keyword in ("小屋", "房子", "场景", "画面")))


def _scene_clarification_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    scene_tags = _scene_semantic_tags(normalized_text)
    question = (
        "这是一条多元素场景指令, 我需要先拆成对象计划。"
        "请补充主要对象数量、位置或风格, 例如先说“确认按小屋、树、小路和云朵生成”。"
    )
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=[],
        scene_plan=ScenePlan(
            intent="clarify_scene",
            summary="识别到多主体场景, 当前规则解析器不会直接执行以避免误画",
            steps=[
                ScenePlanStep(
                    step_id="clarify-scene",
                    title="确认场景对象和布局",
                    intent="ask_clarification",
                    target={"semantic_tags": scene_tags},
                    operation_indexes=[],
                )
            ],
            expected_object_count=None,
        ),
        confidence=0.42,
        requires_confirmation=True,
        clarification_question=question,
        risk_level="medium",
        explanation="识别到多主体或全局改造指令, 需要先确认拆解方案",
    )


def _target_selector(text: str, *, include_layer: bool = True, include_color: bool = True) -> dict[str, Any]:
    many_hint = any(keyword in text for keyword in ("所有", "全部", "都", "整体"))
    target: dict[str, Any] = {"selector": "all" if many_hint else "latest"}
    shape = _find_shape(text)
    if shape and many_hint:
        target["type"] = shape
    semantic_tag = _target_semantic_tag(text)
    if semantic_tag and semantic_tag not in {"house"}:
        target["selector"] = "all"
        target["semantic_tag"] = semantic_tag
    if include_layer:
        layer_id = _extract_layer_id(text)
        if layer_id:
            target["selector"] = "all"
            target["layer_id"] = layer_id
    if include_color:
        colors = _find_all_colors(text)
        if colors and many_hint:
            target["color"] = colors[0][1]
    return target


def _is_many_target(target: dict[str, Any]) -> bool:
    return target.get("selector") == "all" or any(key in target for key in ("semantic_tag", "layer_id", "group_id", "color"))


def _decorate_object(text: str, obj: dict[str, Any]) -> dict[str, Any]:
    object_name = _extract_object_name(text)
    if object_name:
        obj["name"] = object_name
    layer_id = _extract_layer_id(text)
    obj["layer_id"] = layer_id or obj.get("layer_id", "base")
    tags = set(obj.get("semantic_tags", []))
    tags.update(_semantic_tags_for_text(text, obj.get("type"), obj.get("name")))
    obj["semantic_tags"] = sorted(tags)
    return obj


def _extract_number(text: str, after: str, default: int) -> int:
    pattern = rf"{after}\s*([0-9]+|[零一二两三四五六七八九十百]+)"
    match = re.search(pattern, text)
    if not match:
        return default
    return chinese_number_to_int(match.group(1)) or default


def _extract_movement_amount(text: str) -> int:
    explicit_pixel = re.search(r"([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:像素|px)", text)
    if explicit_pixel:
        return chinese_number_to_int(explicit_pixel.group(1)) or 20
    if "一点" in text:
        return 20
    return _extract_number(text, "(?:移动|右|左|上|下)", 20)


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


def _polygon_points(cx: int, cy: int, radius: int, sides: int) -> list[dict[str, float]]:
    return [
        {
            "x": round(cx + radius * math.cos(-math.pi / 2 + index * 2 * math.pi / sides), 2),
            "y": round(cy + radius * math.sin(-math.pi / 2 + index * 2 * math.pi / sides), 2),
        }
        for index in range(sides)
    ]


def _path_commands_for_text(text: str, x: int, y: int) -> list[dict[str, Any]]:
    if "云" in text:
        return [
            {"cmd": "M", "x": x - 150, "y": y + 35},
            {"cmd": "C", "x1": x - 145, "y1": y - 35, "x2": x - 75, "y2": y - 75, "x": x - 20, "y": y - 35},
            {"cmd": "C", "x1": x + 10, "y1": y - 105, "x2": x + 115, "y2": y - 85, "x": x + 125, "y": y - 15},
            {"cmd": "C", "x1": x + 185, "y1": y - 5, "x2": x + 175, "y2": y + 70, "x": x + 95, "y": y + 70},
            {"cmd": "L", "x": x - 110, "y": y + 70},
            {"cmd": "C", "x1": x - 180, "y1": y + 70, "x2": x - 205, "y2": y + 10, "x": x - 150, "y": y + 35},
            {"cmd": "Z"},
        ]
    if "路" in text or "道路" in text:
        return [
            {"cmd": "M", "x": x - 210, "y": y + 130},
            {"cmd": "C", "x1": x - 120, "y1": y + 20, "x2": x + 95, "y2": y + 25, "x": x + 210, "y": y - 120},
        ]
    return [
        {"cmd": "M", "x": x - 180, "y": y + 40},
        {"cmd": "C", "x1": x - 80, "y1": y - 130, "x2": x + 85, "y2": y + 150, "x": x + 180, "y": y - 40},
    ]


def _bezier_commands(x: int, y: int) -> list[dict[str, Any]]:
    return [
        {"cmd": "M", "x": x - 220, "y": y + 70},
        {"cmd": "C", "x1": x - 90, "y1": y - 145, "x2": x + 95, "y2": y + 145, "x": x + 220, "y": y - 70},
    ]


def _make_object(text: str, shape: str) -> dict[str, Any]:
    x, y = _position(text)
    style = _base_style(text)
    if shape == "circle":
        radius = _extract_number(text, "半径", 80)
        return _decorate_object(text, {"type": "circle", "name": "圆形", "geometry": {"cx": x, "cy": y, "radius": radius}, "style": style})
    if shape == "rect":
        width = _extract_number(text, "宽", 220)
        height = _extract_number(text, "高", 140)
        return _decorate_object(text, {
            "type": "rect",
            "name": "矩形",
            "geometry": {"x": x - width // 2, "y": y - height // 2, "width": width, "height": height, "radius": 8},
            "style": style,
        })
    if shape == "ellipse":
        return _decorate_object(text, {"type": "ellipse", "name": "椭圆", "geometry": {"cx": x, "cy": y, "rx": 140, "ry": 80}, "style": style})
    if shape == "triangle":
        return _decorate_object(text, {"type": "triangle", "name": "三角形", "geometry": {"x": x, "y": y, "size": 180}, "style": style})
    if shape in {"line", "arrow"}:
        return _decorate_object(text, {
            "type": shape,
            "name": "箭头" if shape == "arrow" else "线条",
            "geometry": {"x1": x - 120, "y1": y + 80, "x2": x + 120, "y2": y - 80},
            "style": {**style, "fill": "transparent", "strokeWidth": 4},
        })
    if shape == "star":
        return _decorate_object(text, {"type": "star", "name": "星星", "geometry": {"cx": x, "cy": y, "outerRadius": 80, "innerRadius": 36, "points": 5}, "style": style})
    if shape == "polygon":
        sides = 6 if "六边形" in text else 5 if "五边形" in text else 5
        return _decorate_object(
            text,
            {
                "type": "polygon",
                "name": "多边形",
                "geometry": {"points": _polygon_points(x, y, _extract_number(text, "半径", 92), sides)},
                "style": style,
            },
        )
    if shape == "path":
        is_cloud = "云" in text
        is_road = "路" in text or "道路" in text
        path_style = (
            {"fill": "#e0f2fe", "stroke": "#0284c7", "strokeWidth": 3, "opacity": 1}
            if is_cloud
            else {**style, "fill": "transparent", "stroke": "#92400e" if is_road else style["stroke"], "strokeWidth": 10 if is_road else 4}
        )
        return _decorate_object(
            text,
            {
                "type": "path",
                "name": "云朵" if is_cloud else "小路" if is_road else "路径",
                "geometry": {"commands": _path_commands_for_text(text, x, y)},
                "style": path_style,
            },
        )
    if shape == "bezier":
        return _decorate_object(
            text,
            {
                "type": "bezier",
                "name": "贝塞尔曲线",
                "geometry": {"commands": _bezier_commands(x, y)},
                "style": {**style, "fill": "transparent", "strokeWidth": 5},
            },
        )
    content_match = CONTENT_PATTERN.search(text)
    content = content_match.group(1).strip() if content_match else "语音文字"
    return _decorate_object(text, {
        "type": "text",
        "name": "文字",
        "geometry": {"x": x, "y": y, "fontSize": 48, "content": content},
        "style": {**style, "fill": style["fill"], "stroke": "transparent"},
    })


def _extract_count(text: str, default: int = 1) -> int:
    match = re.search(r"([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:个|颗|条|张|扇)?", text)
    if not match:
        return default
    return max(1, min(chinese_number_to_int(match.group(1)) or default, 12))


def _multi_star_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    count = _extract_count(normalized_text, 3)
    style = _base_style(normalized_text)
    left_to_right = "从左到右" in normalized_text or "左到右" in normalized_text
    shrinking = "变小" in normalized_text or "逐渐小" in normalized_text
    start_x = 280
    gap = 170 if count <= 4 else 110
    operations: list[OperationRequest] = []
    for index in range(count):
        outer_radius = 88 - index * 18 if shrinking else 72
        outer_radius = max(34, outer_radius)
        x = start_x + index * gap if left_to_right else 512 + (index - count // 2) * gap
        operations.append(
            OperationRequest(
                operation_type="add_object",
                payload={
                    "object": {
                        "type": "star",
                        "name": f"星星{index + 1}",
                        "layer_id": "middle",
                        "semantic_tags": ["shape.star", "star"],
                        "geometry": {
                            "cx": x,
                            "cy": 384,
                            "outerRadius": outer_radius,
                            "innerRadius": round(outer_radius * 0.45, 2),
                            "points": 5,
                        },
                        "style": style,
                    }
                },
            )
        )
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent="compose_scene",
            summary=f"绘制 {count} 颗星星",
            steps=[ScenePlanStep(step_id="stars", title="绘制星星序列", intent="add_repeated_objects", operation_indexes=list(range(count)))],
            expected_object_count=count,
        ),
        confidence=0.88,
    )


def _house_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    operations = [
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": "房子主体",
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.body", "shape.rect"],
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
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.roof", "shape.triangle"],
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
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.door", "shape.rect"],
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
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.window", "shape.rect"],
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
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.window", "shape.rect"],
                    "geometry": {"x": 570, "y": 380, "width": 64, "height": 64, "radius": 4},
                    "style": {"fill": "#7dd3fc", "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
                }
            },
        ),
    ]
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent="compose_scene",
            summary="绘制带屋顶、门和窗户的房子",
            steps=[
                ScenePlanStep(step_id="house-shell", title="绘制房子结构", intent="add_group", operation_indexes=[0, 1]),
                ScenePlanStep(step_id="house-details", title="绘制门窗细节", intent="add_details", operation_indexes=[2, 3, 4]),
            ],
            expected_object_count=5,
        ),
        confidence=0.9,
    )


def _sun_cloud_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    operations = [
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "circle",
                    "name": "太阳",
                    "layer_id": "background",
                    "semantic_tags": ["shape.circle", "sun"],
                    "geometry": {"cx": 512, "cy": 180, "radius": 72},
                    "style": {"fill": "#facc15", "stroke": "#f97316", "strokeWidth": 3, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "path",
                    "name": "云朵",
                    "layer_id": "middle",
                    "semantic_tags": ["cloud", "path"],
                    "geometry": {"commands": _path_commands_for_text("云", 512, 330)},
                    "style": {"fill": "#e0f2fe", "stroke": "#0284c7", "strokeWidth": 3, "opacity": 1},
                }
            },
        ),
    ]
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent="compose_scene",
            summary="绘制太阳和云朵",
            steps=[ScenePlanStep(step_id="sun-cloud", title="绘制天空元素", intent="add_related_objects", operation_indexes=[0, 1])],
            expected_object_count=2,
        ),
        confidence=0.82,
    )


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
        title_match = TITLE_PATTERN.search(normalized)
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
    elif "太阳" in normalized and "云" in normalized and any(keyword in normalized for keyword in ("画", "创建", "添加")):
        return _sun_cloud_plan(text, normalized)
    elif _needs_scene_planner(normalized):
        return _scene_clarification_plan(text, normalized)
    elif "房子" in normalized and any(keyword in normalized for keyword in ("画", "创建", "添加")):
        return _house_plan(text, normalized)
    elif "星" in normalized and _extract_count(normalized, 1) > 1:
        return _multi_star_plan(text, normalized)
    elif any(keyword in normalized for keyword in ("命名为", "名字叫")) and not any(keyword in normalized for keyword in ("画", "创建", "新建", "保存")):
        object_name = _extract_object_name(normalized)
        if object_name:
            target = {"selector": "latest"} if "它" in normalized else _target_selector(normalized, include_layer=False, include_color=False)
            operation_type = "set_metadata_many" if _is_many_target(target) else "set_metadata"
            operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "name": object_name}))
    elif any(keyword in normalized for keyword in ("放到", "移到", "移动到", "置于")) and _extract_layer_id(normalized) and "画" not in normalized:
        target = _target_selector(normalized, include_layer=False)
        operation_type = "set_metadata_many" if _is_many_target(target) else "set_metadata"
        operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "layer_id": _extract_layer_id(normalized)}))
    elif "所有" in normalized and any(keyword in normalized for keyword in ("改成", "换成")):
        colors = _find_all_colors(normalized)
        source_color = colors[0][1] if colors else None
        target_color = colors[1][1] if len(colors) > 1 else _find_color(normalized)
        if source_color:
            target = _target_selector(normalized, include_color=False)
            target["selector"] = "all"
            target["color"] = source_color
            operations.append(
                OperationRequest(
                    operation_type="set_style_many",
                    payload={"target": target, "style": {"fill": target_color, "stroke": target_color}},
                )
            )
        if "整体" in normalized and ("上" in normalized or "下" in normalized or "左" in normalized or "右" in normalized):
            amount = _extract_movement_amount(normalized)
            dx = amount if "右" in normalized else -amount if "左" in normalized else 0
            dy = amount if "下" in normalized else -amount if "上" in normalized else 0
            operations.append(OperationRequest(operation_type="move_many", payload={"target": {"selector": "all"}, "dx": dx, "dy": dy}))
    elif any(keyword in normalized for keyword in ("改成", "换成", "加粗")):
        style: dict[str, Any] = {}
        if any(color in normalized for color in COLOR_MAP):
            style["fill"] = _find_color(normalized)
        if "加粗" in normalized:
            style["strokeWidth"] = 5
        target = _target_selector(normalized)
        operation_type = "set_style_many" if _is_many_target(target) else "set_style"
        operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "style": style}))
    elif "移动" in normalized or "往" in normalized or "向" in normalized:
        amount = _extract_movement_amount(normalized)
        dx = amount if "右" in normalized else -amount if "左" in normalized else 0
        dy = amount if "下" in normalized else -amount if "上" in normalized else 0
        target = _target_selector(normalized)
        operation_type = "move_many" if _is_many_target(target) else "move_object"
        operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "dx": dx, "dy": dy}))
    elif "放大" in normalized or "缩小" in normalized or "变大" in normalized or "变小" in normalized:
        factor = 2 if "一倍" in normalized or "两倍" in normalized else 1.2
        if "缩小" in normalized or "变小" in normalized:
            factor = 0.5 if "一半" in normalized or "一倍" in normalized else 0.8
        target = _target_selector(normalized)
        operation_type = "scale_many" if _is_many_target(target) else "scale_object"
        operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "factor": factor}))
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
