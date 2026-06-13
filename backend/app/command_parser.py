from __future__ import annotations

import re
import math
from typing import Any

from .schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep
from .render_strategy import classify_render_strategy


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
VOICE_NOISE_STRIP_PATTERN = re.compile(r"[\s\.,!?;:，。！？；：、“”‘’'\"（）()【】\[\]{}<>《》·…~～\-—_]+")
CONTENT_PATTERN = re.compile(r"(?:写|内容是|文字是|文本是)(.+)$")
TITLE_PATTERN = re.compile(r"(?:名字叫|命名为|叫)([\u4e00-\u9fa5a-zA-Z0-9_-]+)")
OBJECT_NAME_PATTERN = re.compile(r"(?:名字叫|命名为|叫)\s*([\u4e00-\u9fa5a-zA-Z0-9_-]{1,16})")
COLOR_CONTEXT_STRIP_PATTERN = re.compile(r"[\s\.,!?;:，。！？；：、“”‘’'\"（）()【】\[\]{}<>《》·…~～\-—_的]+")
COLOR_LINK_WORDS = ("是", "为", "设为", "设置为", "设置成", "改为", "改成", "变为", "变成", "用", "使用", "涂成", "刷成", "画成")
POSITION_RANK_PATTERN = re.compile(r"第?\s*([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:个|棵|扇|座|条|张|块|只|件)")
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
    ("眼睛", "portrait.eye"),
    ("头发", "portrait.hair"),
    ("嘴巴", "portrait.mouth"),
    ("鼻子", "portrait.nose"),
    ("头像", "portrait"),
    ("肖像", "portrait"),
    ("人物", "portrait"),
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
IMAGE_POLISH_HINTS = ("精修", "丰富", "润色", "美化", "增强", "提升质感", "重新渲染", "风格化")
GROUP_SCOPE_HINTS = ("整个", "整座", "整棵", "整扇", "整组", "整张", "全部这", "这一整")
VOICE_NOISE_EXACT_TOKENS = {
    "",
    "嗯",
    "嗯嗯",
    "嗯哼",
    "呃",
    "呃呃",
    "呃嗯",
    "啊",
    "啊啊",
    "哦",
    "噢",
    "唔",
    "唔嗯",
    "哎",
    "诶",
    "欸",
    "那个",
    "这个",
    "然后",
    "接着",
    "卡",
    "需要漏",
    "hmm",
    "hm",
    "um",
    "umm",
    "uh",
    "uhh",
    "er",
    "err",
    "em",
    "emm",
    "eh",
    "ah",
    "oh",
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
    normalized = WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized


def compact_voice_text(text: str) -> str:
    return VOICE_NOISE_STRIP_PATTERN.sub("", normalize_text(text))


def is_voice_noise_input(text: str) -> bool:
    compact = compact_voice_text(text)
    if compact in VOICE_NOISE_EXACT_TOKENS:
        return True
    if re.fullmatch(r"[嗯呃啊哦噢唔哎诶欸]+", compact):
        return True
    if re.fullmatch(r"(?:h+m+|u+h+|u+m+|e+r+|e+m+|a+h+|o+h+)", compact):
        return True
    return False


def _voice_noise_clarification_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=[],
        confidence=0.12,
        requires_confirmation=True,
        clarification_question="我听到的是口头语或噪声, 请直接说要画什么、怎么改或要执行的操作。",
        risk_level="low",
        explanation="识别到口头语或噪声输入, 已跳过复杂规划",
    )


def _find_color(text: str, default: str = "#2563eb") -> str:
    # 先匹配长颜色名, 避免“浅蓝色”被“蓝色”提前命中。
    for name in SORTED_COLOR_NAMES:
        if name in text:
            return COLOR_MAP[name]
    return default


def _find_all_colors(text: str) -> list[tuple[str, str]]:
    return [(name, COLOR_MAP[name]) for name in SORTED_COLOR_NAMES if name in text]


def _compact_color_context(text: str) -> str:
    return COLOR_CONTEXT_STRIP_PATTERN.sub("", text)


def _color_display_name(color: str) -> str:
    for name, value in COLOR_MAP.items():
        if value == color:
            return name
    return "彩色"


def _find_component_color(text: str, target_words: tuple[str, ...], default: str) -> str:
    compact = _compact_color_context(text)
    if not compact:
        return default

    for color_name in SORTED_COLOR_NAMES:
        for target_word in target_words:
            if f"{color_name}{target_word}" in compact:
                return COLOR_MAP[color_name]

    for target_word in target_words:
        for link_word in COLOR_LINK_WORDS:
            for color_name in SORTED_COLOR_NAMES:
                if f"{target_word}{link_word}{color_name}" in compact:
                    return COLOR_MAP[color_name]

    best_match: tuple[int, int, str] | None = None
    for target_word in target_words:
        for target_match in re.finditer(re.escape(target_word), compact):
            for color_name in SORTED_COLOR_NAMES:
                for color_match in re.finditer(re.escape(color_name), compact):
                    gap = target_match.start() - (color_match.start() + len(color_name))
                    if 0 <= gap <= 4:
                        candidate = (gap, color_match.start(), COLOR_MAP[color_name])
                        if best_match is None or candidate[:2] < best_match[:2]:
                            best_match = candidate
    return best_match[2] if best_match else default


def _find_house_body_color(text: str, default: str) -> str:
    compact = _compact_color_context(text)
    for color_name in SORTED_COLOR_NAMES:
        if any(f"{color_name}{target_word}" in compact for target_word in ("房子", "小屋", "房屋")):
            return COLOR_MAP[color_name]
    return _find_component_color(text, ("房子主体", "墙体", "墙面", "房身", "主体", "墙"), default)


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


def _extract_position_rank(text: str) -> int | None:
    match = POSITION_RANK_PATTERN.search(text)
    if not match:
        return None
    rank = chinese_number_to_int(match.group(1))
    return rank if rank and rank > 0 else None


def _is_group_scope_target(text: str, semantic_tag: str | None = None) -> bool:
    if any(hint in text for hint in GROUP_SCOPE_HINTS):
        return True
    return semantic_tag == "tree" and "棵" in text


def _semantic_tags_for_text(text: str, shape: str | None = None, object_name: str | None = None) -> list[str]:
    source = f"{text} {object_name or ''}"
    tags = {tag for keyword, tag in SEMANTIC_KEYWORDS if keyword in source}
    if shape:
        tags.add(f"shape.{shape}")
    return sorted(tags)


def _target_semantic_tag(text: str) -> str | None:
    matches = [(text.rfind(keyword), len(keyword), tag) for keyword, tag in SEMANTIC_KEYWORDS if keyword in text]
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item[0], item[1]))[-1][2]


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
    if semantic_tag and (semantic_tag not in {"house"} or _is_group_scope_target(text, semantic_tag)):
        target["selector"] = "all"
        target["semantic_tag"] = semantic_tag
    if semantic_tag and _is_group_scope_target(text, semantic_tag):
        target["selector"] = "all"
        target["include_group_members"] = True
    if include_layer:
        layer_id = _extract_layer_id(text)
        if layer_id:
            target["selector"] = "all"
            target["layer_id"] = layer_id
    if include_color:
        colors = _find_all_colors(text)
        if colors and many_hint:
            target["color"] = colors[0][1]
        if "暖色" in text:
            target["selector"] = "all"
            target["color_group"] = "warm"
        elif "冷色" in text:
            target["selector"] = "all"
            target["color_group"] = "cool"
        elif "中性色" in text:
            target["selector"] = "all"
            target["color_group"] = "neutral"
    if "小物件" in text or "小对象" in text or "小图形" in text:
        target["selector"] = "all"
        target["size_class"] = "small"
        target["max_area"] = 25000
    if "左边" in text or "左侧" in text:
        target["position"] = "leftmost"
    elif "右边" in text or "右侧" in text:
        target["position"] = "rightmost"
    elif "上方" in text or "顶部" in text:
        target["position"] = "topmost"
    elif "下方" in text or "底部" in text:
        target["position"] = "bottommost"
    rank = _extract_position_rank(text)
    if rank is not None and "position" in target:
        target["selector"] = "all"
        target["position_rank"] = rank
    if "屋顶下面" in text or "屋顶下方" in text:
        target["selector"] = "all"
        target["relative_to"] = {"relation": "below", "target": {"selector": "all", "semantic_tag": "house.roof"}}
    return target


def _is_many_target(target: dict[str, Any]) -> bool:
    return target.get("selector") == "all" or any(
        key in target
        for key in (
            "semantic_tag",
            "semantic_tags",
            "layer_id",
            "group_id",
            "color",
            "color_group",
            "relative_to",
            "position_rank",
            "size_class",
            "include_group_members",
        )
    )


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
    body_color = _find_house_body_color(normalized_text, "#faf7ed")
    roof_color = _find_component_color(normalized_text, ("屋顶", "房顶"), "#dc2626")
    door_color = _find_component_color(normalized_text, ("大门", "门"), "#2563eb")
    window_color = _find_component_color(normalized_text, ("窗户", "窗"), "#7dd3fc")
    operations = [
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": "房子主体" if body_color == "#faf7ed" else f"{_color_display_name(body_color)}房子主体",
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.body", "shape.rect"],
                    "geometry": {"x": 350, "y": 330, "width": 320, "height": 240, "radius": 6},
                    "style": {"fill": body_color, "stroke": "#111827", "strokeWidth": 3, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "triangle",
                    "name": f"{_color_display_name(roof_color)}屋顶",
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.roof", "shape.triangle"],
                    "geometry": {"x": 510, "y": 270, "size": 380},
                    "style": {"fill": roof_color, "stroke": "#111827", "strokeWidth": 3, "opacity": 1},
                }
            },
        ),
        OperationRequest(
            operation_type="add_object",
            payload={
                "object": {
                    "type": "rect",
                    "name": f"{_color_display_name(door_color)}门",
                    "layer_id": "middle",
                    "group_id": "house",
                    "semantic_tags": ["house", "house.door", "shape.rect"],
                    "geometry": {"x": 475, "y": 440, "width": 70, "height": 130, "radius": 4},
                    "style": {"fill": door_color, "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
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
                    "style": {"fill": window_color, "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
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
                    "style": {"fill": window_color, "stroke": "#111827", "strokeWidth": 2, "opacity": 1},
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


def _portrait_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    skin = "#fde68a" if "暖" in normalized_text else "#f8d7b3"
    hair = "#111827" if "黑" in normalized_text else "#7c2d12"
    operations = [
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "ellipse", "name": "肩膀", "layer_id": "middle", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.shoulder"], "geometry": {"cx": 512, "cy": 600, "rx": 220, "ry": 92}, "style": {"fill": "#dbeafe", "stroke": "#1e3a8a", "strokeWidth": 3, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "rect", "name": "脖子", "layer_id": "middle", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.neck"], "geometry": {"x": 462, "y": 455, "width": 100, "height": 112, "radius": 24}, "style": {"fill": skin, "stroke": "#7c2d12", "strokeWidth": 2, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "ellipse", "name": "脸部", "layer_id": "middle", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.face"], "geometry": {"cx": 512, "cy": 340, "rx": 132, "ry": 162}, "style": {"fill": skin, "stroke": "#7c2d12", "strokeWidth": 3, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "path", "name": "头发", "layer_id": "foreground", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.hair"], "geometry": {"commands": [{"cmd": "M", "x": 380, "y": 330}, {"cmd": "C", "x1": 395, "y1": 160, "x2": 620, "y2": 125, "x": 650, "y": 320}, {"cmd": "C", "x1": 610, "y1": 245, "x2": 540, "y2": 235, "x": 505, "y": 245}, {"cmd": "C", "x1": 455, "y1": 240, "x2": 420, "y2": 270, "x": 380, "y": 330}, {"cmd": "Z"}]}, "style": {"fill": hair, "stroke": "#111827", "strokeWidth": 3, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "circle", "name": "左眼", "layer_id": "foreground", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.eye"], "geometry": {"cx": 462, "cy": 340, "radius": 12}, "style": {"fill": "#111827", "stroke": "#111827", "strokeWidth": 2, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "circle", "name": "右眼", "layer_id": "foreground", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.eye"], "geometry": {"cx": 562, "cy": 340, "radius": 12}, "style": {"fill": "#111827", "stroke": "#111827", "strokeWidth": 2, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "path", "name": "鼻子", "layer_id": "foreground", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.nose"], "geometry": {"commands": [{"cmd": "M", "x": 512, "y": 358}, {"cmd": "C", "x1": 500, "y1": 392, "x2": 535, "y2": 398, "x": 516, "y": 418}]}, "style": {"fill": "transparent", "stroke": "#92400e", "strokeWidth": 4, "opacity": 1}}},
        ),
        OperationRequest(
            operation_type="add_object",
            payload={"object": {"type": "path", "name": "嘴巴", "layer_id": "foreground", "group_id": "portrait", "semantic_tags": ["portrait", "portrait.mouth"], "geometry": {"commands": [{"cmd": "M", "x": 462, "y": 435}, {"cmd": "C", "x1": 492, "y1": 468, "x2": 542, "y2": 468, "x": 572, "y": 435}]}, "style": {"fill": "transparent", "stroke": "#dc2626", "strokeWidth": 5, "opacity": 1}}},
        ),
    ]
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent="compose_scene",
            summary="绘制一个可继续编辑的人物头像",
            steps=[
                ScenePlanStep(step_id="portrait-base", title="绘制头像轮廓", intent="add_group", operation_indexes=[0, 1, 2, 3]),
                ScenePlanStep(step_id="portrait-details", title="绘制五官细节", intent="add_details", operation_indexes=[4, 5, 6, 7]),
            ],
            expected_object_count=len(operations),
        ),
        confidence=0.86,
    )


def _programmatic_render_clarification_plan(raw_text: str, normalized_text: str, matched_keywords: tuple[str, ...]) -> CommandPlan:
    keywords = list(matched_keywords)
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=[],
        scene_plan=ScenePlan(
            intent="clarify_programmatic_render",
            summary="识别到结构精确类图形, 当前应进入程序生成或结构化图表规划",
            steps=[
                ScenePlanStep(
                    step_id="clarify-programmatic-render",
                    title="确认结构化图表计划",
                    intent="ask_clarification",
                    target={"render_mode": "programmatic", "matched_keywords": keywords},
                    operation_indexes=[],
                )
            ],
            expected_object_count=None,
        ),
        confidence=0.42,
        requires_confirmation=True,
        clarification_question="这是结构精确类图形, 请补充节点、泳道、模块或关系, 我会优先用程序生成可编辑对象。",
        risk_level="medium",
        explanation="结构图、UML、ER、泳道图等不适合直接生图, 需要先拆成结构化计划",
    )


def _generated_image_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    prompt = normalized_text
    for prefix in ("生成一张", "生成一个", "生成一幅", "生成", "生图", "画一张", "画一个", "画一幅", "画一张图"):
        prompt = prompt.replace(prefix, "")
    prompt = prompt.strip() or normalized_text
    width, height = (1024, 768) if "背景" in normalized_text else (512, 512)
    layer_id = "background" if "背景" in normalized_text else "middle"
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "x": 0 if layer_id == "background" else 256,
        "y": 0 if layer_id == "background" else 128,
        "name": "生成背景" if layer_id == "background" else "生成图片",
        "layer_id": layer_id,
        "semantic_tags": ["generated.image", "image", "render_strategy.generative_image"],
    }
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=[OperationRequest(operation_type="generate_image_asset", payload=payload)],
        scene_plan=ScenePlan(
            intent="generate_asset",
            summary="调用文字转图片 Provider 生成图片对象",
            steps=[ScenePlanStep(step_id="generate-image", title="生成图片素材", intent="generate_asset", operation_indexes=[0])],
            expected_object_count=1,
        ),
        confidence=0.78,
        explanation="准备生成图片素材并作为可编辑图片对象加入画布",
    )


def _polish_image_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    style_prompt = normalized_text
    replacements = {
        "精修我的图片": "精修当前画布, 保留主要构图, 丰富细节, 提升质感",
        "精修当前图片": "精修当前画布, 保留主要构图, 丰富细节, 提升质感",
        "精修当前画面": "精修当前画布, 保留主要构图, 丰富细节, 提升质感",
        "丰富我的图片": "丰富当前画布, 保留主要构图, 增加细节和层次",
        "丰富当前图片": "丰富当前画布, 保留主要构图, 增加细节和层次",
        "美化当前图片": "美化当前画布, 保留主要构图, 提升视觉完成度",
    }
    for source, target in replacements.items():
        style_prompt = style_prompt.replace(source, target)
    if style_prompt == normalized_text:
        style_prompt = f"{normalized_text}, 保留当前画布的主体构图和对象位置"
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=[
            OperationRequest(
                operation_type="polish_image_asset",
                payload={
                    "prompt": style_prompt,
                    "x": 0,
                    "y": 0,
                    "width": 1024,
                    "height": 768,
                    "name": "精修版本",
                    "layer_id": "foreground",
                },
            )
        ],
        scene_plan=ScenePlan(
            intent="polish_artwork",
            summary="将当前画布截图和精修提示词一起发送给图生图模型",
            steps=[ScenePlanStep(step_id="polish-image", title="精修当前画布", intent="image_to_image", operation_indexes=[0])],
            expected_object_count=1,
        ),
        confidence=0.8,
        explanation="准备截取当前画布并调用图生图精修模型",
    )


def _cozy_cabin_scene_plan(raw_text: str, normalized_text: str) -> CommandPlan:
    operations = [
        OperationRequest(operation_type="add_object", payload={"object": {"type": "rect", "name": "浅蓝天空", "layer_id": "background", "group_id": "cabin-scene", "semantic_tags": ["scene", "sky"], "geometry": {"x": 0, "y": 0, "width": 1024, "height": 768, "radius": 0}, "style": {"fill": "#dbeafe", "stroke": "#dbeafe", "strokeWidth": 0, "opacity": 1}}}),
        OperationRequest(operation_type="add_object", payload={"object": {"type": "circle", "name": "太阳", "layer_id": "background", "group_id": "cabin-scene", "semantic_tags": ["sun", "shape.circle"], "geometry": {"cx": 820, "cy": 130, "radius": 58}, "style": {"fill": "#facc15", "stroke": "#f97316", "strokeWidth": 3, "opacity": 1}}}),
        OperationRequest(operation_type="add_object", payload={"object": {"type": "path", "name": "云朵1", "layer_id": "middle", "group_id": "cabin-scene", "semantic_tags": ["cloud", "path"], "geometry": {"commands": _path_commands_for_text("云", 260, 140)}, "style": {"fill": "#eff6ff", "stroke": "#93c5fd", "strokeWidth": 3, "opacity": 1}}}),
        OperationRequest(operation_type="add_object", payload={"object": {"type": "path", "name": "云朵2", "layer_id": "middle", "group_id": "cabin-scene", "semantic_tags": ["cloud", "path"], "geometry": {"commands": _path_commands_for_text("云", 520, 105)}, "style": {"fill": "#eff6ff", "stroke": "#93c5fd", "strokeWidth": 3, "opacity": 1}}}),
        OperationRequest(operation_type="add_object", payload={"object": {"type": "path", "name": "弯曲小路", "layer_id": "middle", "group_id": "cabin-scene", "semantic_tags": ["road", "path"], "geometry": {"commands": _path_commands_for_text("小路", 690, 610)}, "style": {"fill": "transparent", "stroke": "#a16207", "strokeWidth": 18, "opacity": 1}}}),
    ]
    operations.extend(_house_plan(raw_text, normalized_text).operations)
    operations.extend(
        [
            OperationRequest(operation_type="add_object", payload={"object": {"type": "rect", "name": "左树树干", "layer_id": "middle", "group_id": "tree-left", "semantic_tags": ["tree", "tree.trunk", "cabin-scene"], "geometry": {"x": 180, "y": 450, "width": 38, "height": 120, "radius": 8}, "style": {"fill": "#92400e", "stroke": "#451a03", "strokeWidth": 2, "opacity": 1}}}),
            OperationRequest(operation_type="add_object", payload={"object": {"type": "circle", "name": "左树树冠", "layer_id": "middle", "group_id": "tree-left", "semantic_tags": ["tree", "tree.crown", "cabin-scene"], "geometry": {"cx": 200, "cy": 405, "radius": 76}, "style": {"fill": "#16a34a", "stroke": "#166534", "strokeWidth": 3, "opacity": 1}}}),
            OperationRequest(operation_type="add_object", payload={"object": {"type": "rect", "name": "远处小树树干", "layer_id": "middle", "group_id": "tree-far", "semantic_tags": ["tree", "tree.trunk", "cabin-scene"], "geometry": {"x": 105, "y": 485, "width": 28, "height": 86, "radius": 8}, "style": {"fill": "#92400e", "stroke": "#451a03", "strokeWidth": 2, "opacity": 1}}}),
            OperationRequest(operation_type="add_object", payload={"object": {"type": "circle", "name": "远处小树树冠", "layer_id": "middle", "group_id": "tree-far", "semantic_tags": ["tree", "tree.crown", "cabin-scene"], "geometry": {"cx": 120, "cy": 452, "radius": 54}, "style": {"fill": "#22c55e", "stroke": "#15803d", "strokeWidth": 3, "opacity": 1}}}),
        ]
    )
    for operation in operations[0:5]:
        tags = set(operation.payload["object"].get("semantic_tags", []))
        tags.add("cabin-scene")
        operation.payload["object"]["semantic_tags"] = sorted(tags)
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent="compose_scene",
            summary="绘制包含天空、云朵、小屋、树和小路的温馨场景",
            steps=[
                ScenePlanStep(step_id="scene-background", title="铺设天空和云朵", intent="add_background", operation_indexes=[0, 1, 2, 3]),
                ScenePlanStep(step_id="scene-house", title="绘制小屋主体和门窗", intent="add_group", operation_indexes=[5, 6, 7, 8, 9]),
                ScenePlanStep(step_id="scene-details", title="添加树和小路", intent="add_details", operation_indexes=[4, 10, 11, 12, 13]),
            ],
            expected_object_count=len(operations),
        ),
        confidence=0.84,
    )


def parse_command(text: str) -> CommandPlan:
    normalized = normalize_text(text)
    render_strategy = classify_render_strategy(normalized)
    operations: list[OperationRequest] = []
    requires_confirmation = False
    risk_level = "low"

    if is_voice_noise_input(normalized):
        return _voice_noise_clarification_plan(text, normalized)

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
    elif render_strategy.mode == "image_polish" or (any(keyword in normalized for keyword in IMAGE_POLISH_HINTS) and any(keyword in normalized for keyword in ("图片", "图像", "画面", "作品", "画布"))):
        return _polish_image_plan(text, normalized)
    elif render_strategy.mode == "generative_image":
        return _generated_image_plan(text, normalized)
    elif any(keyword in normalized for keyword in ("生成", "生图")) and any(keyword in normalized for keyword in ("图片", "图像", "照片", "肖像", "头像", "背景", "素材")):
        return _generated_image_plan(text, normalized)
    elif any(keyword in normalized for keyword in ("人物肖像", "肖像", "头像")) and any(keyword in normalized for keyword in ("画", "创建", "添加")):
        return _portrait_plan(text, normalized)
    elif "太阳" in normalized and "云" in normalized and any(keyword in normalized for keyword in ("画", "创建", "添加")):
        return _sun_cloud_plan(text, normalized)
    elif any(keyword in normalized for keyword in ("温馨的小屋", "温馨小屋")) and "树" in normalized and ("路" in normalized or "小路" in normalized):
        return _cozy_cabin_scene_plan(text, normalized)
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
    elif any(keyword in normalized for keyword in ("改成", "换成")) and (replacement_shape := _find_shape(normalized)) and "画" not in normalized:
        target = _target_selector(normalized, include_color=False)
        operation_type = "replace_shape_many" if _is_many_target(target) else "replace_shape"
        operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "shape": replacement_shape}))
    elif any(keyword in normalized for keyword in ("改成", "换成", "加粗")):
        style: dict[str, Any] = {}
        if any(color in normalized for color in COLOR_MAP):
            style["fill"] = _find_color(normalized)
        if "加粗" in normalized:
            style["strokeWidth"] = 5
        if style:
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
    elif "放大" in normalized or "缩小" in normalized or "变大" in normalized or "变小" in normalized or "改大" in normalized or "改小" in normalized:
        factor = 2 if "一倍" in normalized or "两倍" in normalized else 1.2
        if "缩小" in normalized or "变小" in normalized or "改小" in normalized:
            factor = 0.5 if "一半" in normalized or "一倍" in normalized else 0.8
        target = _target_selector(normalized)
        operation_type = "scale_many" if _is_many_target(target) else "scale_object"
        operations.append(OperationRequest(operation_type=operation_type, payload={"target": target, "factor": factor}))
    else:
        shape = _find_shape(normalized)
        if shape:
            operations.append(OperationRequest(operation_type="add_object", payload={"object": _make_object(normalized, shape)}))

    if not operations and render_strategy.mode == "programmatic":
        return _programmatic_render_clarification_plan(text, normalized, render_strategy.matched_keywords)

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
