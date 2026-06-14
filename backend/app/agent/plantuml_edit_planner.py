from __future__ import annotations

import re
from typing import Any

from ..command_parser import COLOR_MAP
from ..schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep


PLANTUML_EDIT_KEYWORDS = ("改成", "改为", "换成", "变成", "增加", "新增", "添加")
DIAGRAM_TAGS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("er图", "er 图", "实体关系图", "实体关系"), "er"),
    (("甘特图", "排期图", "项目排期", "进度计划"), "gantt"),
    (("泳道图",), "swimlane"),
    (("组织结构", "组织架构", "团队架构", "团队结构"), "org"),
    (("时序图", "序列图"), "sequence"),
    (("类图", "uml图", "uml"), "class"),
    (("系统架构", "技术架构", "应用架构", "架构图", "结构图"), "component"),
    (("流程图",), "activity"),
)
RENAME_WORDS = ("改成", "改为", "换成", "变成")
ADD_WORDS = ("增加", "新增", "添加")


def build_plantuml_edit_plan(raw_text: str, normalized_text: str) -> CommandPlan | None:
    if not any(keyword in normalized_text for keyword in PLANTUML_EDIT_KEYWORDS):
        return None
    operation_payload = _operation_payload_for_text(normalized_text)
    if operation_payload is None:
        return None
    operation = OperationRequest(operation_type="edit_plantuml", payload=operation_payload)
    action_text = _action_title(operation_payload)
    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=[operation],
        scene_plan=ScenePlan(
            intent="edit_plantuml_source",
            summary=f"通过语音修改 PlantUML 图表源码: {action_text}",
            steps=[
                ScenePlanStep(
                    step_id="agent-plantuml-edit-1",
                    title=action_text,
                    intent="edit_plantuml",
                    target=operation_payload["target"],
                    operation_indexes=[0],
                )
            ],
            expected_object_count=1,
        ),
        confidence=0.8,
        requires_confirmation=False,
        risk_level="low",
        explanation=f"准备修改 PlantUML 图表: {action_text}",
        planner_source="agent",
    )


def _operation_payload_for_text(text: str) -> dict[str, Any] | None:
    if "加粗" in text or any(color_name in text for color_name in COLOR_MAP):
        return None
    diagram_type = _diagram_type_for_text(text)
    if diagram_type is None and not any(keyword in text for keyword in ("plantuml", "图表")):
        return None
    target = {"selector": "all", "type": "plantuml"}
    if diagram_type:
        target["semantic_tag"] = f"plantuml.{diagram_type}"

    rename_payload = _rename_payload(text)
    if rename_payload:
        return {"target": target, **rename_payload}

    add_payload = _add_payload(text, diagram_type)
    if add_payload:
        return {"target": target, **add_payload}
    return None


def _diagram_type_for_text(text: str) -> str | None:
    for keywords, diagram_type in DIAGRAM_TAGS:
        if any(keyword in text for keyword in keywords):
            return diagram_type
    return None


def _clean_fragment(value: str) -> str:
    cleaned = value.strip(" ，,。；;:：、 \t\n\r")
    for prefix in ("把", "将", "给", "在", "从"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip(" ，,。；;:：、 ")
    for marker in ("里的", "中的", "里面的", "内的", "里", "中", "内"):
        if marker in cleaned:
            cleaned = cleaned.rsplit(marker, 1)[-1]
    cleaned = re.sub(r"(节点|任务|泳道|关系|关联)$", "", cleaned).strip(" ，,。；;:：、 ")
    return cleaned


def _rename_payload(text: str) -> dict[str, Any] | None:
    matches = [(text.rfind(word), word) for word in RENAME_WORDS if word in text]
    if not matches:
        return None
    position, word = sorted(matches)[-1]
    old_text = _clean_fragment(text[:position])
    new_text = _clean_fragment(text[position + len(word) :])
    if not old_text or not new_text:
        return None
    return {"action": "rename", "old_text": old_text, "new_text": new_text}


def _extract_after_add_word(text: str) -> str | None:
    matches = [(text.rfind(word), word) for word in ADD_WORDS if word in text]
    if not matches:
        return None
    position, word = sorted(matches)[-1]
    return _clean_fragment(text[position + len(word) :])


def _add_payload(text: str, diagram_type: str | None) -> dict[str, Any] | None:
    item = _extract_after_add_word(text)
    if not item:
        return None
    if "关系" in text or "关联" in text:
        return {"action": "add_relation", "relation_text": item}
    if "泳道" in text or diagram_type == "swimlane":
        lane_name = re.sub(r"(泳道)$", "", item).strip(" ，,。；;:：、 ") or item
        return {"action": "add_swimlane", "lane_name": lane_name, "step_name": f"{lane_name}处理"}
    if "任务" in text or diagram_type == "gantt":
        task_name = re.sub(r"(任务)$", "", item).strip(" ，,。；;:：、 ") or item
        return {"action": "add_gantt_task", "task_name": task_name}
    if "节点" in text or "步骤" in text or diagram_type in {"activity", "org"}:
        node_text = re.sub(r"(节点|步骤)$", "", item).strip(" ，,。；;:：、 ") or item
        return {"action": "add_node", "node_text": node_text}
    return None


def _action_title(payload: dict[str, Any]) -> str:
    action = payload.get("action")
    if action == "rename":
        return f"把 {payload.get('old_text')} 改成 {payload.get('new_text')}"
    if action == "add_gantt_task":
        return f"增加甘特任务 {payload.get('task_name')}"
    if action == "add_swimlane":
        return f"增加泳道 {payload.get('lane_name')}"
    if action == "add_relation":
        return f"增加关系 {payload.get('relation_text')}"
    if action == "add_node":
        return f"增加节点 {payload.get('node_text')}"
    return "修改 PlantUML 图表"
