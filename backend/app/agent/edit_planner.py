from __future__ import annotations

import re
from typing import Any

from ..command_parser import COLOR_MAP, SHAPE_MAP, chinese_number_to_int
from ..schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep


EDIT_KEYWORDS = ("改成", "换成", "变成", "设为", "设置为", "移动", "往", "向", "放大", "缩小", "变大", "变小", "改大", "改小", "加粗")
CREATE_KEYWORDS = ("画", "创建", "生成", "新建", "添加")
CLAUSE_SPLIT_PATTERN = re.compile(r"(?:，|,|。|；|;|并且|同时|然后|接着|并)")
NUMBER_PATTERN = re.compile(r"([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:像素|px)?")


TARGET_RULES: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (("房子的窗户", "小屋的窗户", "房子窗户", "窗户"), {"selector": "all", "semantic_tags": ["house.window", "window"]}),
    (("房子的门", "小屋的门", "房子门", "门"), {"selector": "all", "semantic_tag": "house.door"}),
    (("屋顶",), {"selector": "all", "semantic_tag": "house.roof"}),
    (("房子主体", "墙体", "墙面"), {"selector": "all", "semantic_tag": "house.body"}),
    (("沙发",), {"selector": "all", "semantic_tag": "sofa"}),
    (("茶几",), {"selector": "all", "semantic_tag": "coffee_table"}),
    (("落地灯", "台灯", "灯"), {"selector": "all", "semantic_tag": "floor_lamp"}),
    (("地毯",), {"selector": "all", "semantic_tag": "rug"}),
    (("流程图节点", "图节点", "节点", "模块"), {"selector": "all", "semantic_tag": "diagram.node"}),
    (("流程图箭头", "连接线", "箭头"), {"selector": "all", "semantic_tag": "diagram.connector"}),
    (("组织结构图节点", "组织节点", "部门卡片", "角色卡片"), {"selector": "all", "semantic_tag": "org_chart.node"}),
    (("甘特图任务条", "任务条", "进度条"), {"selector": "all", "semantic_tag": "gantt_chart.task_bar"}),
    (("里程碑",), {"selector": "all", "semantic_tag": "gantt_chart.milestone"}),
    (("海报标题", "主标题"), {"selector": "all", "semantic_tag": "poster.headline"}),
    (("卖点文字", "卖点"), {"selector": "all", "semantic_tag": "poster.feature_text"}),
    (("按钮", "行动按钮", "cta"), {"selector": "all", "semantic_tags": ["poster.cta", "ui.cta"]}),
    (("侧边导航", "侧边栏"), {"selector": "all", "semantic_tag": "ui.sidebar"}),
    (("搜索框",), {"selector": "all", "semantic_tag": "ui.search"}),
    (("所有文字", "全部文字", "所有文本", "全部文本"), {"selector": "all", "type": "text"}),
)


def _copy_target(target: dict[str, Any]) -> dict[str, Any]:
    copied = dict(target)
    if "semantic_tags" in copied:
        copied["semantic_tags"] = list(copied["semantic_tags"])
    return copied


def _find_color(text: str) -> str | None:
    colors = [(name, value) for name, value in COLOR_MAP.items() if name in text]
    if not colors:
        return None
    return sorted(colors, key=lambda item: (text.rfind(item[0]) + len(item[0]), len(item[0])))[-1][1]


def _find_shape(text: str) -> str | None:
    matches = [(name, value) for name, value in SHAPE_MAP.items() if name in text]
    if not matches:
        return None
    return sorted(matches, key=lambda item: text.rfind(item[0]))[-1][1]


def _movement_amount(text: str) -> int:
    if "一点" in text or "稍微" in text:
        return 20
    match = NUMBER_PATTERN.search(text)
    if not match:
        return 20
    return chinese_number_to_int(match.group(1)) or 20


def _movement_delta(text: str) -> tuple[int, int] | None:
    if not any(keyword in text for keyword in ("移动", "往", "向")):
        return None
    amount = _movement_amount(text)
    dx = amount if "右" in text else -amount if "左" in text else 0
    dy = amount if "下" in text else -amount if "上" in text else 0
    if dx == 0 and dy == 0:
        return None
    return dx, dy


def _scale_factor(text: str) -> float | None:
    if not any(keyword in text for keyword in ("放大", "缩小", "变大", "变小", "改大", "改小")):
        return None
    if "缩小" in text or "变小" in text or "改小" in text:
        return 0.5 if "一半" in text or "一倍" in text else 0.8
    return 2 if "一倍" in text or "两倍" in text else 1.2


def _target_for_clause(clause: str) -> tuple[dict[str, Any] | None, str | None]:
    for keywords, target in TARGET_RULES:
        if any(keyword in clause for keyword in keywords):
            return _copy_target(target), keywords[0]
    if "它" in clause or "这个" in clause or "刚才" in clause:
        return {"selector": "latest"}, None
    return None, None


def _target_is_specific(target: dict[str, Any] | None) -> bool:
    return bool(target and any(key in target for key in ("semantic_tag", "semantic_tags", "type", "layer_id", "group_id")))


def _build_style_operation(clause: str, target: dict[str, Any]) -> OperationRequest | None:
    style: dict[str, Any] = {}
    color = _find_color(clause)
    if color and any(keyword in clause for keyword in ("改成", "换成", "变成", "设为", "设置为", "涂成", "刷成")):
        style["fill"] = color
        style["stroke"] = color
    if "加粗" in clause:
        style["strokeWidth"] = 5
    if not style:
        return None
    operation_type = "set_style_many" if _target_is_specific(target) else "set_style"
    return OperationRequest(operation_type=operation_type, payload={"target": target, "style": style})


def _build_replace_operation(clause: str, target: dict[str, Any]) -> OperationRequest | None:
    if not any(keyword in clause for keyword in ("改成", "换成", "变成")):
        return None
    shape = _find_shape(clause)
    if not shape:
        return None
    operation_type = "replace_shape_many" if _target_is_specific(target) else "replace_shape"
    return OperationRequest(operation_type=operation_type, payload={"target": target, "shape": shape})


def _build_move_operation(clause: str, target: dict[str, Any]) -> OperationRequest | None:
    delta = _movement_delta(clause)
    if delta is None:
        return None
    dx, dy = delta
    operation_type = "move_many" if _target_is_specific(target) else "move_object"
    return OperationRequest(operation_type=operation_type, payload={"target": target, "dx": dx, "dy": dy})


def _build_scale_operation(clause: str, target: dict[str, Any]) -> OperationRequest | None:
    factor = _scale_factor(clause)
    if factor is None:
        return None
    operation_type = "scale_many" if _target_is_specific(target) else "scale_object"
    return OperationRequest(operation_type=operation_type, payload={"target": target, "factor": factor})


def _split_clauses(text: str) -> list[str]:
    clauses = [clause.strip() for clause in CLAUSE_SPLIT_PATTERN.split(text) if clause.strip()]
    return clauses or [text]


def build_local_edit_plan(raw_text: str, normalized_text: str) -> CommandPlan | None:
    if any(keyword in normalized_text for keyword in CREATE_KEYWORDS):
        return None
    if not any(keyword in normalized_text for keyword in EDIT_KEYWORDS):
        return None

    operations: list[OperationRequest] = []
    steps: list[ScenePlanStep] = []
    active_target: dict[str, Any] | None = None
    has_specific_target = False

    for clause in _split_clauses(normalized_text):
        clause_target, matched_keyword = _target_for_clause(clause)
        if clause_target is not None:
            active_target = clause_target
            has_specific_target = has_specific_target or _target_is_specific(clause_target)
        if active_target is None:
            continue

        clause_operations = [
            operation
            for operation in (
                _build_replace_operation(clause, active_target),
                _build_style_operation(clause, active_target),
                _build_move_operation(clause, active_target),
                _build_scale_operation(clause, active_target),
            )
            if operation is not None
        ]
        if not clause_operations:
            continue

        start_index = len(operations)
        operations.extend(clause_operations)
        steps.append(
            ScenePlanStep(
                step_id=f"agent-edit-{len(steps) + 1}",
                title=f"编辑{matched_keyword or '当前对象'}",
                intent="edit_existing_objects",
                target=active_target,
                operation_indexes=list(range(start_index, len(operations))),
            )
        )

    if not operations or not has_specific_target:
        return None

    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent="edit_scene",
            summary="Agent 将语音编辑指令拆成可验证的对象修改操作",
            steps=steps,
            expected_object_count=None,
        ),
        confidence=0.78,
        requires_confirmation=False,
        risk_level="low",
        explanation=f"准备编辑 {len(operations)} 个步骤",
        planner_source="agent",
    )
