from __future__ import annotations

import re

COLOR_MAP: dict[str, str] = {
    "红色": "#dc2626",
    "蓝色": "#2563eb",
    "浅蓝色": "#7dd3fc",
    "深蓝色": "#1d4ed8",
    "粉红色": "#f9a8d4",
    "淡粉色": "#fbcfe8",
    "浅粉色": "#fbcfe8",
    "粉色": "#f9a8d4",
    "紫色": "#9333ea",
    "青色": "#06b6d4",
    "青蓝色": "#0891b2",
    "绿色": "#16a34a",
    "浅绿色": "#86efac",
    "深绿色": "#15803d",
    "黄色": "#facc15",
    "橙色": "#f97316",
    "棕色": "#92400e",
    "黑色": "#111827",
    "白色": "#ffffff",
    "米白色": "#faf7ed",
    "灰色": "#6b7280",
    "透明": "transparent",
    # 常用简称与缩写兜底，避免 ASR 转写略去“色”或带有其他尾缀
    "红": "#dc2626",
    "蓝": "#2563eb",
    "绿": "#16a34a",
    "黄": "#facc15",
    "黑": "#111827",
    "白": "#ffffff",
    "灰": "#6b7280",
    "紫": "#9333ea",
    "粉": "#f9a8d4",
    "青": "#06b6d4",
    "橙": "#f97316",
    "棕": "#92400e",
    "天蓝": "#7dd3fc",
    "深蓝": "#1d4ed8",
    "浅蓝": "#7dd3fc",
    "粉红": "#f9a8d4",
    "深绿": "#15803d",
    "浅绿": "#86efac",
    "咖啡": "#92400e",
}

SHAPE_MAP: dict[str, str] = {
    "平行四边形": "parallelogram",
    "菱形": "diamond",
    "钻石形": "diamond",
    "梯形": "trapezoid",
    "十字形": "cross",
    "十字": "cross",
    "爱心": "heart",
    "心形": "heart",
    "上弦月": "moon",
    "下弦月": "moon",
    "满月": "moon",
    "圆月": "moon",
    "半月": "moon",
    "新月": "moon",
    "盈月": "moon",
    "亏月": "moon",
    "残月": "moon",
    "缺月": "moon",
    "月相": "moon",
    "对话气泡": "speech_bubble",
    "聊天气泡": "speech_bubble",
    "气泡": "speech_bubble",
    "六瓣花": "flower",
    "五瓣花": "flower",
    "花朵": "flower",
    "花": "flower",
    "月牙形": "crescent",
    "月牙": "moon",
    "月亮": "moon",
    "圆环": "ring",
    "空心圆": "ring",
    "圆柱": "cylinder",
    "数据库形状": "cylinder",
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
    "边形": "polygon",
    "路径": "path",
    "曲线": "bezier",
    "贝塞尔曲线": "bezier",
    "贝塞尔": "bezier",
    "云朵": "cloud",
    "云": "cloud",
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
NUMBER_TOKEN = r"[0-9]+|[零一二两三四五六七八九十百]+"
COLOR_CONTEXT_STRIP_PATTERN = re.compile(r"[\s\.,!?;:，。！？；：、“”‘’'\"（）()【】\[\]{}<>《》·…~～\-—_的]+")


def chinese_number_to_int(text: str) -> int | None:
    text = text.strip()
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


def find_color(text: str, default: str = "#2563eb") -> str:
    for name in SORTED_COLOR_NAMES:
        if name in text:
            return COLOR_MAP[name]
    return default


def find_all_colors(text: str) -> list[tuple[str, str]]:
    return [(name, COLOR_MAP[name]) for name in SORTED_COLOR_NAMES if name in text]


def compact_color_context(text: str) -> str:
    return COLOR_CONTEXT_STRIP_PATTERN.sub("", text)


def color_display_name(color: str) -> str:
    for name, value in COLOR_MAP.items():
        if value == color:
            return name
    return "彩色"


def find_shape(text: str) -> str | None:
    for name in SORTED_SHAPE_NAMES:
        if name in text:
            return SHAPE_MAP[name]
    return None


def extract_number(text: str, slot_word: str, default: int) -> int:
    after_match = re.search(rf"{slot_word}\s*({NUMBER_TOKEN})", text)
    if after_match:
        return chinese_number_to_int(after_match.group(1)) or default
    if re.fullmatch(r"[\u4e00-\u9fa5]+", slot_word):
        before_match = re.search(rf"({NUMBER_TOKEN})\s*{slot_word}", text)
        if before_match:
            return chinese_number_to_int(before_match.group(1)) or default
    return default


def extract_count(text: str, default: int = 1, max_count: int = 12) -> int:
    match = re.search(rf"({NUMBER_TOKEN})\s*(?:个|颗|条|张|扇)?", text)
    if not match:
        return default
    return max(1, min(chinese_number_to_int(match.group(1)) or default, max_count))


def extract_draw_count(text: str, default: int = 1, max_count: int = 12) -> int:
    match = re.search(rf"(?:画|创建|添加|生成)\s*({NUMBER_TOKEN})\s*(?:个|颗|朵|条|张|扇|座|块|只|件)", text)
    if not match:
        return default
    return max(1, min(chinese_number_to_int(match.group(1)) or default, max_count))


def extract_polygon_sides(text: str, default: int = 5) -> int:
    return max(3, min(extract_number(text, "边", default), 12))


def extract_petals(text: str, default: int = 6) -> int:
    return max(3, min(extract_number(text, "瓣", default), 12))
