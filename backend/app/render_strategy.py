from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


RenderMode = Literal["programmatic", "generative_image", "image_polish", "undecided"]
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class RenderStrategy:
    mode: RenderMode
    reason: str
    matched_keywords: tuple[str, ...] = ()


PROGRAMMATIC_RENDER_KEYWORDS = (
    "甘特图",
    "排期图",
    "泳道图",
    "流程图",
    "uml图",
    "uml",
    "er图",
    "er 图",
    "系统架构图",
    "系统架构",
    "架构图",
    "组织结构图",
    "组织结构",
    "组织架构",
    "团队架构",
    "普通小房子",
    "小房子",
    "房子",
    "草地",
    "太阳",
    "树",
    "简单场景组合",
    "海报草稿版式",
    "海报草稿",
    "手抄报草稿版式",
    "手抄报草稿",
    "版式草稿",
)

GENERATIVE_IMAGE_KEYWORDS = (
    "水墨画",
    "水墨",
    "二次元动漫人物",
    "二次元",
    "动漫人物",
    "写实插画",
    "写实风格插画",
    "概念场景图",
    "概念场景",
    "复杂艺术海报",
    "艺术海报",
    "风格转换",
    "商业视觉图",
    "商业视觉",
    "儿童插画",
    "国风插画",
    "科幻场景",
    "科幻概念",
)

IMAGE_POLISH_KEYWORDS = (
    "精修图片",
    "精修我的图片",
    "精修当前图片",
    "精修当前画面",
    "丰富我的图片",
    "丰富当前图片",
    "风格化",
    "重新渲染",
)

IMAGE_ACTION_KEYWORDS = ("画", "生成", "创建", "生图", "做一张", "来一张")


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(keyword for keyword in keywords if keyword in text)


def _normalize_strategy_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text.strip().lower())


def classify_render_strategy(text: str) -> RenderStrategy:
    normalized = _normalize_strategy_text(text)
    polish_matches = _matched_keywords(normalized, IMAGE_POLISH_KEYWORDS)
    if polish_matches:
        return RenderStrategy("image_polish", "图生图精修或风格化应使用图片模型", polish_matches)

    programmatic_matches = _matched_keywords(normalized, PROGRAMMATIC_RENDER_KEYWORDS)
    generative_matches = _matched_keywords(normalized, GENERATIVE_IMAGE_KEYWORDS)

    if programmatic_matches and "草稿版式" in normalized:
        return RenderStrategy("programmatic", "草稿版式需要文字清晰、位置稳定和后续可编辑", programmatic_matches)
    if generative_matches:
        return RenderStrategy("generative_image", "艺术风格和复杂视觉表现更适合生图模型", generative_matches)
    if programmatic_matches:
        return RenderStrategy("programmatic", "结构精确类图形需要程序渲染和可编辑对象", programmatic_matches)

    if any(keyword in normalized for keyword in IMAGE_ACTION_KEYWORDS) and any(keyword in normalized for keyword in ("插画", "视觉图", "概念图")):
        return RenderStrategy("generative_image", "开放式视觉素材更适合生图模型", ())
    return RenderStrategy("undecided", "未命中特定渲染策略", ())
