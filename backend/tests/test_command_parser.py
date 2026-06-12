from __future__ import annotations

import pytest

from app.command_parser import chinese_number_to_int, parse_command


def test_chinese_number_to_int() -> None:
    assert chinese_number_to_int("三") == 3
    assert chinese_number_to_int("两") == 2
    assert chinese_number_to_int("十二") == 12
    assert chinese_number_to_int("一百") == 100


@pytest.mark.parametrize("text", ["嗯。", "hmm.", "然后。", "卡。", "需要漏。"])
def test_parse_voice_noise_short_circuits_to_clarification(text: str) -> None:
    plan = parse_command(text)

    assert plan.operations == []
    assert plan.requires_confirmation is True
    assert plan.confidence == 0.12
    assert plan.clarification_question == "我听到的是口头语或噪声, 请直接说要画什么、怎么改或要执行的操作。"
    assert plan.explanation == "识别到口头语或噪声输入, 已跳过复杂规划"


def test_parse_command_after_filler_word_still_draws() -> None:
    plan = parse_command("然后画一个蓝色圆形")

    assert plan.operations[0].operation_type == "add_object"
    assert plan.operations[0].payload["object"]["type"] == "circle"


def test_parse_create_canvas() -> None:
    plan = parse_command("新建一张横向白色画布")
    assert plan.operations[0].operation_type == "create_canvas"
    assert plan.operations[0].payload["background"] == "#ffffff"
    assert plan.operations[0].payload["width"] == 1280
    assert plan.operations[0].payload["height"] == 720


def test_parse_circle_with_color_and_size() -> None:
    plan = parse_command("画一个蓝色圆形在中间 半径一百")
    op = plan.operations[0]
    assert op.operation_type == "add_object"
    assert op.payload["object"]["type"] == "circle"
    assert op.payload["object"]["style"]["fill"] == "#2563eb"
    assert op.payload["object"]["geometry"]["radius"] == 100


def test_parse_object_name_layer_and_semantic_tags() -> None:
    plan = parse_command("画一个黄色圆形 命名为太阳 放到前景层")
    obj = plan.operations[0].payload["object"]
    assert obj["name"] == "太阳"
    assert obj["layer_id"] == "foreground"
    assert "sun" in obj["semantic_tags"]
    assert "shape.circle" in obj["semantic_tags"]


def test_parse_polygon_path_and_bezier_shapes() -> None:
    polygon_plan = parse_command("画一个绿色五边形在左边")
    polygon = polygon_plan.operations[0].payload["object"]
    assert polygon["type"] == "polygon"
    assert len(polygon["geometry"]["points"]) == 5

    path_plan = parse_command("画一条弯曲小路")
    path = path_plan.operations[0].payload["object"]
    assert path["type"] == "path"
    assert path["name"] == "小路"
    assert path["style"]["strokeWidth"] == 10

    bezier_plan = parse_command("画一条棕色贝塞尔曲线在中间")
    bezier = bezier_plan.operations[0].payload["object"]
    assert bezier["type"] == "bezier"
    assert bezier["style"]["fill"] == "transparent"


def test_parse_complex_house_plan() -> None:
    plan = parse_command("画一个房子 红色屋顶 蓝色门 两扇窗户")
    assert [op.payload["object"]["name"] for op in plan.operations] == ["房子主体", "红色屋顶", "蓝色门", "窗户1", "窗户2"]
    assert plan.scene_plan is not None
    assert plan.scene_plan.expected_object_count == 5
    assert plan.operations[3].payload["object"]["semantic_tags"] == ["house", "house.window", "shape.rect"]


def test_parse_sun_and_cloud_as_two_step_plan() -> None:
    plan = parse_command("画一个太阳然后在下面加一片云")
    assert [op.operation_type for op in plan.operations] == ["add_object", "add_object"]
    assert [op.payload["object"]["type"] for op in plan.operations] == ["circle", "path"]
    assert plan.scene_plan is not None
    assert plan.scene_plan.expected_object_count == 2


def test_parse_multi_object_scene_requires_planner_clarification() -> None:
    plan = parse_command("画一个温馨的小屋 左边有两棵树 右边有一条弯曲小路 天空有三朵云")
    assert plan.requires_confirmation is True
    assert plan.operations == []
    assert plan.confidence == 0.42
    assert plan.scene_plan is not None
    assert plan.scene_plan.intent == "clarify_scene"
    assert plan.explanation == "识别到多主体或全局改造指令, 需要先确认拆解方案"


def test_parse_undo_synonym() -> None:
    plan = parse_command("退回一步")
    assert plan.operations[0].operation_type == "undo"


def test_parse_multiple_stars_left_to_right_shrinking() -> None:
    plan = parse_command("画三颗黄色星星 从左到右变小")
    assert len(plan.operations) == 3
    assert [op.operation_type for op in plan.operations] == ["add_object", "add_object", "add_object"]
    objects = [op.payload["object"] for op in plan.operations]
    assert [obj["name"] for obj in objects] == ["星星1", "星星2", "星星3"]
    assert objects[0]["geometry"]["cx"] < objects[1]["geometry"]["cx"] < objects[2]["geometry"]["cx"]
    assert objects[0]["geometry"]["outerRadius"] > objects[1]["geometry"]["outerRadius"] > objects[2]["geometry"]["outerRadius"]
    assert objects[0]["style"]["fill"] == "#facc15"


def test_parse_batch_color_change_and_move() -> None:
    plan = parse_command("把所有蓝色图形改成绿色 然后整体向上移动一点")
    assert [op.operation_type for op in plan.operations] == ["set_style_many", "move_many"]
    assert plan.operations[0].payload["target"]["color"] == "#2563eb"
    assert plan.operations[0].payload["style"]["fill"] == "#16a34a"
    assert plan.operations[1].payload["dy"] == -20


def test_parse_scale_latest_object() -> None:
    plan = parse_command("把它放大一倍")
    assert plan.operations[0].operation_type == "scale_object"
    assert plan.operations[0].payload["factor"] == 2


def test_parse_semantic_scale_many() -> None:
    plan = parse_command("把房子的窗户都变大")
    assert plan.operations[0].operation_type == "scale_many"
    assert plan.operations[0].payload["target"]["semantic_tag"] == "house.window"
    assert plan.operations[0].payload["factor"] == 1.2


def test_parse_layer_move_many() -> None:
    plan = parse_command("把前景层所有对象向右移动一点")
    assert plan.operations[0].operation_type == "move_many"
    assert plan.operations[0].payload["target"]["layer_id"] == "foreground"
    assert plan.operations[0].payload["dx"] == 20


def test_parse_rename_latest_object() -> None:
    plan = parse_command("把它命名为太阳")
    assert plan.operations[0].operation_type == "set_metadata"
    assert plan.operations[0].payload["target"] == {"selector": "latest"}
    assert plan.operations[0].payload["name"] == "太阳"
