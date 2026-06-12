from __future__ import annotations

from app.command_parser import chinese_number_to_int, parse_command


def test_chinese_number_to_int() -> None:
    assert chinese_number_to_int("三") == 3
    assert chinese_number_to_int("两") == 2
    assert chinese_number_to_int("十二") == 12
    assert chinese_number_to_int("一百") == 100


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


def test_parse_complex_house_plan() -> None:
    plan = parse_command("画一个房子 红色屋顶 蓝色门 两扇窗户")
    assert [op.payload["object"]["name"] for op in plan.operations] == ["房子主体", "红色屋顶", "蓝色门", "窗户1", "窗户2"]


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
