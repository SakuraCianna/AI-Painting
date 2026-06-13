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


def test_parse_house_component_colors_from_voice_text() -> None:
    plan = parse_command("画一个房子，蓝色屋顶，红色门，黄色窗户。")
    objects = [op.payload["object"] for op in plan.operations]
    roof = next(obj for obj in objects if "house.roof" in obj["semantic_tags"])
    door = next(obj for obj in objects if "house.door" in obj["semantic_tags"])
    windows = [obj for obj in objects if "house.window" in obj["semantic_tags"]]

    assert roof["style"]["fill"] == "#2563eb"
    assert door["style"]["fill"] == "#dc2626"
    assert all(window["style"]["fill"] == "#facc15" for window in windows)


def test_parse_sun_and_cloud_as_two_step_plan() -> None:
    plan = parse_command("画一个太阳然后在下面加一片云")
    assert [op.operation_type for op in plan.operations] == ["add_object", "add_object"]
    assert [op.payload["object"]["type"] for op in plan.operations] == ["circle", "path"]
    assert plan.scene_plan is not None
    assert plan.scene_plan.expected_object_count == 2


def test_parse_multi_object_scene_requires_planner_clarification() -> None:
    plan = parse_command("把画面改成夜晚 保留房子的形状 给窗户加暖黄色灯光")
    assert plan.requires_confirmation is True
    assert plan.operations == []
    assert plan.confidence == 0.42
    assert plan.scene_plan is not None
    assert plan.scene_plan.intent == "clarify_scene"
    assert plan.explanation == "识别到多主体或全局改造指令, 需要先确认拆解方案"


def test_parse_undo_synonym() -> None:
    plan = parse_command("退回一步")
    assert plan.operations[0].operation_type == "undo"


def test_parse_clear_canvas_requires_confirmation() -> None:
    plan = parse_command("清空画布")

    assert plan.requires_confirmation is True
    assert plan.risk_level == "high"
    assert plan.operations[0].operation_type == "clear_canvas"
    assert plan.clarification_question == "清空画布会删除当前所有对象, 请说确认清空或取消"


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


def test_parse_portrait_scene_as_vector_group() -> None:
    plan = parse_command("画一个人物肖像")
    assert len(plan.operations) == 8
    assert [operation.operation_type for operation in plan.operations] == ["add_object"] * 8
    assert plan.scene_plan is not None
    assert plan.scene_plan.expected_object_count == 8
    assert any("portrait.eye" in operation.payload["object"]["semantic_tags"] for operation in plan.operations)


def test_parse_text_to_image_asset_generation() -> None:
    plan = parse_command("生成一张人物肖像画")
    assert plan.operations[0].operation_type == "generate_image_asset"
    assert plan.operations[0].payload["width"] == 512
    assert plan.operations[0].payload["semantic_tags"] == ["generated.image", "image", "render_strategy.generative_image"]
    assert plan.scene_plan is not None
    assert plan.scene_plan.intent == "generate_asset"


def test_parse_artistic_image_requests_use_generation_strategy() -> None:
    plan = parse_command("画一个二次元动漫人物")

    assert plan.operations[0].operation_type == "generate_image_asset"
    assert "二次元动漫人物" in plan.operations[0].payload["prompt"]
    assert "render_strategy.generative_image" in plan.operations[0].payload["semantic_tags"]


def test_parse_programmatic_diagram_requests_do_not_use_image_generation() -> None:
    plan = parse_command("画一个泳道图, 包含销售、运营和交付")

    assert all(operation.operation_type != "generate_image_asset" for operation in plan.operations)
    assert plan.requires_confirmation is True
    assert plan.scene_plan is not None
    assert plan.scene_plan.intent == "clarify_programmatic_render"
    assert plan.scene_plan.steps[0].target["render_mode"] == "programmatic"


def test_parse_polish_current_image() -> None:
    plan = parse_command("精修我的图片")
    assert plan.operations[0].operation_type == "polish_image_asset"
    assert "精修当前画布" in plan.operations[0].payload["prompt"]
    assert plan.scene_plan is not None
    assert plan.scene_plan.intent == "polish_artwork"


def test_parse_window_shape_replacement_and_spatial_scale() -> None:
    replace_plan = parse_command("把窗户改成圆形")
    assert replace_plan.operations[0].operation_type == "replace_shape_many"
    assert replace_plan.operations[0].payload["target"]["semantic_tag"] == "house.window"
    assert replace_plan.operations[0].payload["shape"] == "circle"

    scale_plan = parse_command("把左边窗户改大一点")
    assert scale_plan.operations[0].operation_type == "scale_many"
    assert scale_plan.operations[0].payload["target"]["semantic_tag"] == "house.window"
    assert scale_plan.operations[0].payload["target"]["position"] == "leftmost"


def test_parse_object_query_dsl_selectors() -> None:
    ranked_plan = parse_command("把左边第二棵树改成黄色")
    ranked_target = ranked_plan.operations[0].payload["target"]
    assert ranked_plan.operations[0].operation_type == "set_style_many"
    assert ranked_target["semantic_tag"] == "tree"
    assert ranked_target["position"] == "leftmost"
    assert ranked_target["position_rank"] == 2
    assert ranked_target["include_group_members"] is True

    relative_plan = parse_command("把屋顶下面的门改成绿色")
    relative_target = relative_plan.operations[0].payload["target"]
    assert relative_target["semantic_tag"] == "house.door"
    assert relative_target["relative_to"] == {"relation": "below", "target": {"selector": "all", "semantic_tag": "house.roof"}}

    near_tree_plan = parse_command("把靠近门的那棵树改成黄色")
    near_tree_target = near_tree_plan.operations[0].payload["target"]
    assert near_tree_plan.operations[0].operation_type == "set_style_many"
    assert near_tree_target["semantic_tag"] == "tree"
    assert near_tree_target["include_group_members"] is True
    assert near_tree_target["relative_to"] == {
        "relation": "near",
        "max_distance": 260,
        "target": {"selector": "all", "semantic_tag": "house.door"},
    }

    covering_image_plan = parse_command("把挡住标题的图片向右移动一点")
    covering_image_target = covering_image_plan.operations[0].payload["target"]
    assert covering_image_plan.operations[0].operation_type == "move_many"
    assert covering_image_target["type"] == "image"
    assert "semantic_tag" not in covering_image_target
    assert covering_image_target["relative_to"] == {
        "relation": "covering",
        "target": {"selector": "all", "semantic_tag": "poster.headline"},
    }

    inside_text_plan = parse_command("把卡片里的文字改成蓝色")
    inside_text_target = inside_text_plan.operations[0].payload["target"]
    assert inside_text_plan.operations[0].operation_type == "set_style_many"
    assert inside_text_target["type"] == "text"
    assert inside_text_target["relative_to"] == {
        "relation": "inside",
        "margin": 8,
        "target": {
            "selector": "all",
            "semantic_tags": ["poster.hero", "ui.hero", "ui.metric", "ui.chart", "infographic.metric_card", "org_chart.node"],
        },
    }

    same_row_button_plan = parse_command("把和标题同一行的按钮改成绿色")
    same_row_button_target = same_row_button_plan.operations[0].payload["target"]
    assert same_row_button_plan.operations[0].operation_type == "set_style_many"
    assert same_row_button_target["semantic_tags"] == ["poster.cta", "ui.cta"]
    assert same_row_button_target["relative_to"] == {
        "relation": "same_row",
        "tolerance": 48,
        "target": {"selector": "all", "semantic_tag": "poster.headline"},
    }

    front_image_plan = parse_command("把标题上层的图片向右移动一点")
    front_image_target = front_image_plan.operations[0].payload["target"]
    assert front_image_plan.operations[0].operation_type == "move_many"
    assert front_image_target["type"] == "image"
    assert front_image_target["relative_to"] == {
        "relation": "front_of",
        "target": {"selector": "all", "semantic_tag": "poster.headline"},
    }

    color_group_plan = parse_command("把所有暖色小物件向上移动一点")
    color_group_target = color_group_plan.operations[0].payload["target"]
    assert color_group_plan.operations[0].operation_type == "move_many"
    assert color_group_target["color_group"] == "warm"
    assert color_group_target["size_class"] == "small"

    group_plan = parse_command("把整个房子向右移动一点")
    group_target = group_plan.operations[0].payload["target"]
    assert group_plan.operations[0].operation_type == "move_many"
    assert group_target["semantic_tag"] == "house"
    assert group_target["include_group_members"] is True


def test_parse_cozy_cabin_scene_as_executable_plan() -> None:
    plan = parse_command("画一个温馨的小屋 左边有两棵树 右边有一条弯曲小路 天空有三朵云")
    assert plan.requires_confirmation is False
    assert len(plan.operations) == 14
    assert plan.scene_plan is not None
    assert plan.scene_plan.expected_object_count == 14
    assert [operation.operation_type for operation in plan.operations] == ["add_object"] * 14


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
