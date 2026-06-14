from __future__ import annotations

import re
from typing import Any

from ..command_parser import COLOR_MAP, SHAPE_MAP, chinese_number_to_int
from ..schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep
from .plantuml_edit_planner import build_plantuml_edit_plan


EDIT_KEYWORDS = ("改成", "换成", "变成", "设为", "设置为", "移动", "往", "向", "放大", "缩小", "变大", "变小", "改大", "改小", "加粗")
CREATE_KEYWORDS = ("画", "创建", "生成", "新建", "添加")
CLAUSE_SPLIT_PATTERN = re.compile(r"(?:，|,|。|；|;|并且|同时|然后|接着|并)")
NUMBER_PATTERN = re.compile(r"([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:像素|px)?")
POSITION_RANK_PATTERN = re.compile(r"第?\s*([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:个|棵|扇|座|条|张|块|只|件)")
GROUP_SCOPE_HINTS = ("整个", "整座", "整棵", "整扇", "整组", "整张", "全部这", "这一整")


TARGET_RULES: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (("房子的窗户", "小屋的窗户", "房子窗户", "窗户"), {"selector": "all", "semantic_tags": ["house.window", "window"]}),
    (("房子的门", "小屋的门", "房子门", "门"), {"selector": "all", "semantic_tag": "house.door"}),
    (("屋顶",), {"selector": "all", "semantic_tag": "house.roof"}),
    (("房子主体", "墙体", "墙面"), {"selector": "all", "semantic_tag": "house.body"}),
    (("房子", "小屋"), {"selector": "all", "semantic_tag": "house"}),
    (("树冠",), {"selector": "all", "semantic_tag": "tree.crown"}),
    (("树", "小树", "大树"), {"selector": "all", "semantic_tag": "tree"}),
    (("沙发",), {"selector": "all", "semantic_tag": "sofa"}),
    (("茶几",), {"selector": "all", "semantic_tag": "coffee_table"}),
    (("落地灯", "台灯", "灯"), {"selector": "all", "semantic_tag": "floor_lamp"}),
    (("地毯",), {"selector": "all", "semantic_tag": "rug"}),
    (("流程图节点", "图节点", "节点", "模块"), {"selector": "all", "semantic_tag": "diagram.node"}),
    (("流程图箭头", "连接线", "箭头"), {"selector": "all", "semantic_tag": "diagram.connector"}),
    (("组织结构图节点", "组织节点", "部门卡片", "角色卡片"), {"selector": "all", "semantic_tag": "org_chart.node"}),
    (("甘特图任务条", "任务条", "进度条"), {"selector": "all", "semantic_tag": "gantt_chart.task_bar"}),
    (("里程碑",), {"selector": "all", "semantic_tag": "gantt_chart.milestone"}),
    (("海报标题", "主标题", "标题"), {"selector": "all", "semantic_tag": "poster.headline"}),
    (("卖点文字", "卖点"), {"selector": "all", "semantic_tag": "poster.feature_text"}),
    (("图片", "图像", "照片"), {"selector": "all", "type": "image"}),
    (("文字", "文本"), {"selector": "all", "type": "text"}),
    (("按钮", "行动按钮", "cta"), {"selector": "all", "semantic_tags": ["poster.cta", "ui.cta"]}),
    (("侧边导航", "侧边栏"), {"selector": "all", "semantic_tag": "ui.sidebar"}),
    (("搜索框",), {"selector": "all", "semantic_tag": "ui.search"}),
    (("所有文字", "全部文字", "所有文本", "全部文本"), {"selector": "all", "type": "text"}),
)


def _copy_target(target: dict[str, Any]) -> dict[str, Any]:
    copied = dict(target)
    if "semantic_tags" in copied:
        copied["semantic_tags"] = list(copied["semantic_tags"])
    if isinstance(copied.get("relative_to"), dict):
        relative_to = dict(copied["relative_to"])
        if isinstance(relative_to.get("target"), dict):
            relative_to["target"] = dict(relative_to["target"])
        copied["relative_to"] = relative_to
    if isinstance(copied.get("relative_to_all"), list):
        copied["relative_to_all"] = [
            {
                **relation,
                "target": dict(relation["target"]) if isinstance(relation.get("target"), dict) else relation.get("target"),
            }
            if isinstance(relation, dict)
            else relation
            for relation in copied["relative_to_all"]
        ]
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


def _find_replacement_shape(text: str) -> str | None:
    link_positions = [(text.rfind(link_word), link_word) for link_word in ("改成", "换成", "变成") if link_word in text]
    if not link_positions:
        return None
    position, link_word = sorted(link_positions)[-1]
    return _find_shape(text[position + len(link_word) :])


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


def _extract_position_rank(text: str) -> int | None:
    match = POSITION_RANK_PATTERN.search(text)
    if not match:
        return None
    rank = chinese_number_to_int(match.group(1))
    return rank if rank and rank > 0 else None


def _is_group_scope_target(text: str, target: dict[str, Any]) -> bool:
    if any(hint in text for hint in GROUP_SCOPE_HINTS):
        return True
    return target.get("semantic_tag") == "tree" and "棵" in text


def _relation_hints_for_clause(clause: str) -> list[dict[str, Any]]:
    relation_hints: list[dict[str, Any]] = []
    if "屋顶下面" in clause or "屋顶下方" in clause:
        relation_hints.append({"relation": "below", "target": {"selector": "all", "semantic_tag": "house.roof"}})
    if any(keyword in clause for keyword in ("靠近门", "门附近", "门旁边", "挨着门", "贴近门")):
        relation_hints.append(
            {
                "relation": "near",
                "max_distance": 260,
                "target": {"selector": "all", "semantic_tag": "house.door"},
            }
        )
    if any(keyword in clause for keyword in ("挡住标题", "遮住标题", "盖住标题", "覆盖标题", "压住标题", "遮挡标题")):
        relation_hints.append({"relation": "covering", "target": {"selector": "all", "semantic_tag": "poster.headline"}})
    if any(keyword in clause for keyword in ("和标题重叠", "与标题重叠", "重叠标题")):
        relation_hints.append({"relation": "overlap", "target": {"selector": "all", "semantic_tag": "poster.headline"}})
    if any(keyword in clause for keyword in ("卡片里的", "卡片里面", "卡片内", "卡片中的", "卡片里")):
        relation_hints.append(
            {
                "relation": "inside",
                "margin": 8,
                "target": {
                    "selector": "all",
                    "semantic_tags": [
                        "poster.hero",
                        "ui.hero",
                        "ui.metric",
                        "ui.chart",
                        "infographic.metric_card",
                        "org_chart.node",
                    ],
                },
            }
        )
    if any(keyword in clause for keyword in ("和标题同一行", "与标题同一行", "标题同一行")):
        relation_hints.append({"relation": "same_row", "tolerance": 48, "target": {"selector": "all", "semantic_tag": "poster.headline"}})
    if any(keyword in clause for keyword in ("和标题同一列", "与标题同一列", "标题同一列")):
        relation_hints.append({"relation": "same_column", "tolerance": 48, "target": {"selector": "all", "semantic_tag": "poster.headline"}})
    if any(keyword in clause for keyword in ("标题前面的", "标题上层的", "图层在标题前面", "盖在标题前面")):
        relation_hints.append({"relation": "front_of", "target": {"selector": "all", "semantic_tag": "poster.headline"}})
    if any(keyword in clause for keyword in ("标题后面的", "标题下层的", "图层在标题后面", "放在标题后面")):
        relation_hints.append({"relation": "behind", "target": {"selector": "all", "semantic_tag": "poster.headline"}})
    return relation_hints


def _apply_query_hints(clause: str, target: dict[str, Any]) -> dict[str, Any]:
    enriched = _copy_target(target)
    if _is_group_scope_target(clause, enriched):
        enriched["selector"] = "all"
        enriched["include_group_members"] = True
    if "左边" in clause or "左侧" in clause:
        enriched["position"] = "leftmost"
    elif "右边" in clause or "右侧" in clause:
        enriched["position"] = "rightmost"
    elif "上方" in clause or "顶部" in clause:
        enriched["position"] = "topmost"
    elif "下方" in clause or "底部" in clause:
        enriched["position"] = "bottommost"

    rank = _extract_position_rank(clause)
    if rank is not None and "position" in enriched:
        enriched["selector"] = "all"
        enriched["position_rank"] = rank

    relation_hints = _relation_hints_for_clause(clause)
    if len(relation_hints) == 1:
        enriched["selector"] = "all"
        enriched["relative_to"] = relation_hints[0]
    elif len(relation_hints) > 1:
        enriched["selector"] = "all"
        enriched["relative_to_all"] = relation_hints

    if "小物件" in clause or "小对象" in clause or "小图形" in clause:
        enriched["selector"] = "all"
        enriched["size_class"] = "small"
        enriched["max_area"] = 25000

    return enriched


def _scale_factor(text: str) -> float | None:
    if not any(keyword in text for keyword in ("放大", "缩小", "变大", "变小", "改大", "改小")):
        return None
    if "缩小" in text or "变小" in text or "改小" in text:
        return 0.5 if "一半" in text or "一倍" in text else 0.8
    return 2 if "一倍" in text or "两倍" in text else 1.2


def _target_for_clause(clause: str) -> tuple[dict[str, Any] | None, str | None]:
    if "暖色" in clause:
        return _apply_query_hints(clause, {"selector": "all", "color_group": "warm"}), "暖色对象"
    if "冷色" in clause:
        return _apply_query_hints(clause, {"selector": "all", "color_group": "cool"}), "冷色对象"
    if "中性色" in clause:
        return _apply_query_hints(clause, {"selector": "all", "color_group": "neutral"}), "中性色对象"
    target_matches: list[tuple[int, int, str, dict[str, Any]]] = []
    for keywords, target in TARGET_RULES:
        matched_keywords = [keyword for keyword in keywords if keyword in clause]
        if not matched_keywords:
            continue
        best_keyword = sorted(matched_keywords, key=lambda keyword: (clause.rfind(keyword) + len(keyword), len(keyword)))[-1]
        target_matches.append((clause.rfind(best_keyword) + len(best_keyword), len(best_keyword), best_keyword, target))
    if target_matches:
        _, _, matched_keyword, target = sorted(target_matches, key=lambda item: (item[0], item[1]))[-1]
        return _apply_query_hints(clause, target), matched_keyword
    if "它" in clause or "这个" in clause or "刚才" in clause:
        return {"selector": "latest"}, None
    return None, None


def _target_is_specific(target: dict[str, Any] | None) -> bool:
    return bool(
        target
        and (
            target.get("selector") == "all"
            or any(
                key in target
                for key in (
                    "semantic_tag",
                    "semantic_tags",
                    "type",
                    "layer_id",
                    "group_id",
                    "color_group",
                    "relative_to",
                    "relative_to_all",
                    "position_rank",
                    "size_class",
                    "include_group_members",
                )
            )
        )
    )


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
    shape = _find_replacement_shape(clause)
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
    plantuml_plan = build_plantuml_edit_plan(raw_text, normalized_text)
    if plantuml_plan is not None:
        return plantuml_plan

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
