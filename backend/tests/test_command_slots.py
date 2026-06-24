from __future__ import annotations

from app.command_slots import (
    chinese_number_to_int,
    extract_draw_count,
    extract_number,
    extract_petals,
    extract_polygon_sides,
    find_color,
    find_shape,
)


def test_chinese_number_to_int_handles_common_forms() -> None:
    assert chinese_number_to_int("十") == 10
    assert chinese_number_to_int("十二") == 12
    assert chinese_number_to_int("二十三") == 23
    assert chinese_number_to_int("一百") == 100
    assert chinese_number_to_int("一百二十三") == 123


def test_color_slot_prefers_longest_matching_name() -> None:
    assert find_color("画一个浅蓝色圆形") == "#7dd3fc"
    assert find_color("画一个深蓝色圆形") == "#1d4ed8"
    assert find_color("画一个粉色五瓣花") == "#f9a8d4"


def test_shape_slot_prefers_specific_shape_names() -> None:
    assert find_shape("画一个平行四边形") == "parallelogram"
    assert find_shape("画一个月牙形") == "crescent"
    assert find_shape("画一个七边形") == "polygon"


def test_number_slot_reads_before_and_after_slot_word() -> None:
    assert extract_number("画一个半径100的圆", "半径", 80) == 100
    assert extract_number("画一个七边形", "边", 5) == 7
    assert extract_number("画一个三瓣花", "瓣", 6) == 3


def test_draw_count_does_not_treat_geometry_size_as_repetition() -> None:
    assert extract_draw_count("画三个粉色圆形") == 3
    assert extract_draw_count("画一个半径100的圆") == 1


def test_parameterized_shape_slots_are_clamped_to_supported_range() -> None:
    assert extract_polygon_sides("画一个二边形") == 3
    assert extract_polygon_sides("画一个二十边形") == 12
    assert extract_petals("画一个二瓣花") == 3
    assert extract_petals("画一个二十瓣花") == 12
