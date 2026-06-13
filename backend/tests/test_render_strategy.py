from __future__ import annotations

from app.render_strategy import classify_render_strategy


def test_programmatic_strategy_prefers_structural_diagrams() -> None:
    cases = [
        "画一个甘特图",
        "创建一个泳道图",
        "生成一个 UML 图",
        "画一个系统架构图",
        "画一个产品团队组织结构图",
        "画一个普通小房子和草地太阳树",
        "画一个海报草稿版式",
        "画一个手抄报草稿版式",
    ]

    for text in cases:
        assert classify_render_strategy(text).mode == "programmatic", text


def test_generative_strategy_prefers_artistic_images() -> None:
    cases = [
        "画一张水墨画",
        "画一个二次元动漫人物",
        "生成一张写实插画",
        "画一个概念场景图",
        "画一个复杂艺术海报",
        "生成一个商业视觉图",
        "画一个儿童插画",
        "画一个国风插画",
        "画一个科幻场景",
    ]

    for text in cases:
        assert classify_render_strategy(text).mode == "generative_image", text


def test_polish_strategy_has_highest_priority() -> None:
    strategy = classify_render_strategy("精修我的图片, 转成国风插画")

    assert strategy.mode == "image_polish"
    assert "精修我的图片" in strategy.matched_keywords
