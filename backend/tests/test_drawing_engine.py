from __future__ import annotations

from pathlib import Path

import pytest

from app.database import connect_db, init_db
from app.drawing_engine import apply_operation, apply_operation_plan, redo_last_operation, undo_last_operation
from app.repositories import create_artwork, get_artwork
from app.schemas import ArtworkCreateRequest, OperationRequest


def _connection(tmp_path: Path):
    db_path = tmp_path / "drawing-engine.sqlite3"
    init_db(str(db_path))
    return connect_db(str(db_path))


def _create_artwork(connection) -> str:
    return create_artwork(connection, ArtworkCreateRequest(title="引擎测试", width=1024, height=768, background="#ffffff")).id


def _add_object(connection, artwork_id: str, obj: dict) -> str:
    apply_operation(connection, artwork_id, OperationRequest(operation_type="add_object", payload={"object": obj}))
    return get_artwork(connection, artwork_id).objects[-1].id


def test_canvas_save_export_and_empty_clear_operations(tmp_path: Path) -> None:
    with _connection(tmp_path) as connection:
        artwork_id = _create_artwork(connection)

        assert apply_operation(
            connection,
            artwork_id,
            OperationRequest(operation_type="create_canvas", payload={"width": 800, "height": 600, "background": "#f8fafc"}),
        ) == "已更新画布"
        assert apply_operation(connection, artwork_id, OperationRequest(operation_type="save_artwork", payload={"title": "版本一"})) == "已保存作品版本"
        assert apply_operation(connection, artwork_id, OperationRequest(operation_type="export_artwork", payload={})) == "已准备导出"
        assert apply_operation(connection, artwork_id, OperationRequest(operation_type="clear_canvas", payload={})) == "画布已经是空的"

        artwork = get_artwork(connection, artwork_id)
        assert artwork.width == 800
        assert artwork.height == 600
        assert artwork.background == "#f8fafc"
        assert artwork.title == "版本一"

        operations = connection.execute("SELECT operation_type FROM operations WHERE artwork_id = ? ORDER BY rowid", (artwork_id,)).fetchall()
        assert [row["operation_type"] for row in operations] == ["create_canvas", "save_artwork", "clear_canvas"]


def test_replace_shape_many_preserves_bounds_and_supports_undo_redo(tmp_path: Path) -> None:
    with _connection(tmp_path) as connection:
        artwork_id = _create_artwork(connection)
        base_style = {"fill": "#e8f0fe", "stroke": "#111827", "strokeWidth": 2}
        objects = [
            {"type": "rect", "name": "矩形", "geometry": {"x": 100, "y": 100, "width": 80, "height": 40}, "style": base_style},
            {"type": "circle", "name": "圆形", "geometry": {"cx": 260, "cy": 120, "radius": 30}, "style": base_style},
            {"type": "ellipse", "name": "椭圆", "geometry": {"cx": 380, "cy": 130, "rx": 60, "ry": 20}, "style": base_style},
            {"type": "triangle", "name": "三角形", "geometry": {"x": 520, "y": 140, "size": 90}, "style": base_style},
            {"type": "star", "name": "星形", "geometry": {"cx": 680, "cy": 150, "outerRadius": 45, "innerRadius": 18, "points": 5}, "style": base_style},
            {
                "type": "polygon",
                "name": "多边形",
                "geometry": {"points": [{"x": 100, "y": 300}, {"x": 180, "y": 300}, {"x": 160, "y": 360}]},
                "style": base_style,
            },
            {
                "type": "path",
                "name": "路径",
                "geometry": {"commands": [{"cmd": "M", "x": 260, "y": 300}, {"cmd": "C", "x1": 300, "y1": 260, "x2": 360, "y2": 360, "x": 400, "y": 300}]},
                "style": base_style,
            },
        ]
        for obj in objects:
            _add_object(connection, artwork_id, obj)

        message = apply_operation(
            connection,
            artwork_id,
            OperationRequest(operation_type="replace_shape_many", payload={"target": {"selector": "all"}, "shape": "ellipse"}),
        )

        replaced = get_artwork(connection, artwork_id).objects
        assert message == "已替换 7 个对象形状"
        assert {obj.type for obj in replaced} == {"ellipse"}
        assert all("rx" in obj.geometry and "ry" in obj.geometry for obj in replaced)

        restored = undo_last_operation(connection, artwork_id)
        assert [obj.type for obj in restored.objects] == [obj["type"] for obj in objects]

        redone = redo_last_operation(connection, artwork_id)
        assert {obj.type for obj in redone.objects} == {"ellipse"}


def test_apply_operation_plan_rolls_back_when_a_step_fails(tmp_path: Path) -> None:
    with _connection(tmp_path) as connection:
        artwork_id = _create_artwork(connection)
        operations = [
            OperationRequest(
                operation_type="add_object",
                payload={"object": {"type": "circle", "name": "临时圆", "geometry": {"cx": 512, "cy": 384, "radius": 80}, "style": {"fill": "#2563eb"}}},
            ),
            OperationRequest(
                operation_type="set_style_many",
                payload={"target": {"semantic_tag": "missing"}, "style": {"fill": "#16a34a"}},
            ),
        ]

        with pytest.raises(KeyError):
            apply_operation_plan(connection, artwork_id, operations)

        assert get_artwork(connection, artwork_id).objects == []
        operation_count = connection.execute("SELECT COUNT(*) AS count FROM operations WHERE artwork_id = ?", (artwork_id,)).fetchone()["count"]
        assert operation_count == 0


def test_operation_plan_undo_and_redo_use_one_history_group(tmp_path: Path) -> None:
    with _connection(tmp_path) as connection:
        artwork_id = _create_artwork(connection)
        operations = [
            OperationRequest(
                operation_type="add_object",
                payload={"object": {"type": "circle", "name": "圆形", "geometry": {"cx": 320, "cy": 384, "radius": 64}, "style": {"fill": "#2563eb"}}},
            ),
            OperationRequest(
                operation_type="add_object",
                payload={"object": {"type": "star", "name": "星形", "geometry": {"cx": 520, "cy": 384, "outerRadius": 72, "innerRadius": 32, "points": 5}, "style": {"fill": "#facc15"}}},
            ),
        ]

        apply_operation_plan(connection, artwork_id, operations)

        rows = connection.execute(
            "SELECT command_group_id, operation_index, status FROM operations WHERE artwork_id = ? ORDER BY operation_index",
            (artwork_id,),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["command_group_id"] == rows[1]["command_group_id"]
        assert [row["operation_index"] for row in rows] == [0, 1]
        assert [obj.type for obj in get_artwork(connection, artwork_id).objects] == ["circle", "star"]

        undone = undo_last_operation(connection, artwork_id)
        assert undone.objects == []
        assert [
            row["status"]
            for row in connection.execute("SELECT status FROM operations WHERE artwork_id = ? ORDER BY operation_index", (artwork_id,)).fetchall()
        ] == ["undone", "undone"]

        redone = redo_last_operation(connection, artwork_id)
        assert [obj.type for obj in redone.objects] == ["circle", "star"]


def test_unsupported_operation_is_rejected(tmp_path: Path) -> None:
    with _connection(tmp_path) as connection:
        artwork_id = _create_artwork(connection)

        with pytest.raises(ValueError, match="Unsupported operation type"):
            apply_operation(connection, artwork_id, OperationRequest(operation_type="unknown", payload={}))
