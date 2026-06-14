from __future__ import annotations

import re
from typing import Any

from ..command_parser import COLOR_MAP, chinese_number_to_int
from ..schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep


PLANTUML_EDIT_KEYWORDS = ("改成", "改为", "换成", "变成", "增加", "新增", "添加", "删除", "移除", "去掉", "删掉", "开始")
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
DELETE_WORDS = ("删除", "移除", "去掉", "删掉")


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
    looks_like_gantt_task_update = _looks_like_gantt_task_update(text)
    if diagram_type is None and not any(keyword in text for keyword in ("plantuml", "图表")) and not looks_like_gantt_task_update:
        return None
    target = {"selector": "all", "type": "plantuml"}
    if diagram_type:
        target["semantic_tag"] = f"plantuml.{diagram_type}"

    update_gantt_task_payload = _update_gantt_task_payload(text, diagram_type, looks_like_gantt_task_update=looks_like_gantt_task_update)
    if update_gantt_task_payload:
        return {"target": target, **update_gantt_task_payload}

    update_relation_payload = _update_relation_payload(text)
    if update_relation_payload:
        return {"target": target, **update_relation_payload}

    delete_payload = _delete_payload(text, diagram_type)
    if delete_payload:
        return {"target": target, **delete_payload}

    add_payload = _add_payload(text, diagram_type)
    if add_payload:
        return {"target": target, **add_payload}

    rename_payload = _rename_payload(text)
    if rename_payload:
        return {"target": target, **rename_payload}
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


def _latest_rename_marker(text: str) -> tuple[int, str] | None:
    matches = [(text.rfind(word), word) for word in RENAME_WORDS if word in text]
    return sorted(matches)[-1] if matches else None


def _duration_days_from_text(text: str) -> int | None:
    match = re.search(r"([0-9]+|[零一二两三四五六七八九十百]+)\s*(?:天|日|days?)", text, re.IGNORECASE)
    if not match:
        return None
    days = chinese_number_to_int(match.group(1))
    if days is None:
        return None
    return max(1, min(days, 365))


def _clean_gantt_task_name(value: str) -> str:
    cleaned = _clean_fragment(value)
    for suffix in ("持续时间", "开始时间", "开始日期", "结束时间", "结束日期", "时长", "耗时", "周期", "日期", "时间", "开始", "结束", "任务"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" 的地得，,。；;:：、 ")
            break
    return _clean_fragment(cleaned)


def _clean_starts_after_task(value: str) -> str:
    cleaned = _clean_fragment(value)
    for suffix in (
        "任务结束后开始",
        "任务完成后开始",
        "结束后开始",
        "完成后开始",
        "任务结束后",
        "任务完成后",
        "结束后",
        "完成后",
        "之后开始",
        "后开始",
        "之后",
        "任务",
    ):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" 的地得，,。；;:：、 ")
            break
    return _clean_fragment(cleaned)


def _looks_like_gantt_task_update(text: str) -> bool:
    if "任务" not in text:
        return False
    return any(keyword in text for keyword in ("时长", "持续", "耗时", "周期", "开始时间", "开始日期", "结束后开始", "完成后开始", "之后开始", "后开始"))


def _update_gantt_task_payload(text: str, diagram_type: str | None, *, looks_like_gantt_task_update: bool = False) -> dict[str, Any] | None:
    if diagram_type != "gantt" and "甘特" not in text and "排期" not in text and not looks_like_gantt_task_update:
        return None
    marker = _latest_rename_marker(text)
    payload: dict[str, Any] = {"action": "update_gantt_task"}
    if marker:
        position, word = marker
        before = text[:position]
        after = text[position + len(word) :]
        if any(keyword in before for keyword in ("时长", "持续", "耗时", "周期")):
            task_name = _clean_gantt_task_name(before)
            duration_days = _duration_days_from_text(after)
            if task_name and duration_days is not None:
                payload["task_name"] = task_name
                payload["duration_days"] = duration_days
        elif any(keyword in before for keyword in ("开始", "日期", "时间")) and any(keyword in after for keyword in ("结束", "完成", "之后", "后")):
            task_name = _clean_gantt_task_name(before)
            starts_after = _clean_starts_after_task(after)
            if task_name and starts_after:
                payload["task_name"] = task_name
                payload["starts_after"] = starts_after
    if "task_name" not in payload:
        match = re.search(r"(?:让|把)?(.+?)任务?从(.+?)任务?(?:结束后|完成后|之后|后)开始", text)
        if match:
            task_name = _clean_gantt_task_name(match.group(1))
            starts_after = _clean_starts_after_task(match.group(2))
            if task_name and starts_after:
                payload["task_name"] = task_name
                payload["starts_after"] = starts_after
    if "task_name" not in payload:
        return None
    if "duration_days" not in payload and "starts_after" not in payload:
        return None
    return payload


def _relation_cardinality_for_text(text: str) -> str | None:
    if any(keyword in text for keyword in ("一对一", "1对1", "一比一")):
        return "one_to_one"
    if any(keyword in text for keyword in ("一对多", "1对多", "一比多")):
        return "one_to_many"
    if any(keyword in text for keyword in ("多对一", "多对1", "多比一")):
        return "many_to_one"
    if any(keyword in text for keyword in ("多对多", "多比多")):
        return "many_to_many"
    return None


def _strip_relation_cardinality(text: str) -> str:
    cleaned = text
    for keyword in ("一对一", "1对1", "一比一", "一对多", "1对多", "一比多", "多对一", "多对1", "多比一", "多对多", "多比多"):
        cleaned = cleaned.replace(keyword, "")
    return cleaned.strip(" 的地得，,。；;:：、 ")


def _relation_endpoints_from_text(text: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"(之间的|之间|间的|间)$", "", text.strip(" 的地得，,。；;:：、 "))
    match = re.search(r"(.+?)(?:和|与|及)(.+)$", cleaned)
    if match is None:
        return None
    source = _clean_fragment(match.group(1))
    target = _clean_fragment(match.group(2))
    if not source or not target:
        return None
    return source, target


def _update_relation_payload(text: str) -> dict[str, Any] | None:
    if "关系" not in text and "关联" not in text:
        return None
    matches = [(text.rfind(word), word) for word in RENAME_WORDS if word in text]
    if not matches:
        return None
    position, word = sorted(matches)[-1]
    relation_text = _clean_fragment(text[:position])
    new_text = _clean_fragment(text[position + len(word) :])
    if not relation_text or not new_text:
        return None
    cardinality = _relation_cardinality_for_text(new_text)
    new_label = _strip_relation_cardinality(new_text)
    payload: dict[str, Any] = {"action": "update_relation", "relation_text": relation_text}
    endpoints = _relation_endpoints_from_text(relation_text)
    if endpoints:
        payload["source_entity"], payload["target_entity"] = endpoints
    if new_label:
        payload["new_label"] = new_label
    if cardinality:
        payload["cardinality"] = cardinality
    if "new_label" not in payload and "cardinality" not in payload:
        return None
    return payload


def _extract_after_add_word(text: str) -> str | None:
    matches = [(text.rfind(word), word) for word in ADD_WORDS if word in text]
    if not matches:
        return None
    position, word = sorted(matches)[-1]
    return _clean_fragment(text[position + len(word) :])


def _extract_after_delete_word(text: str) -> str | None:
    matches = [(text.rfind(word), word) for word in DELETE_WORDS if word in text]
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


def _delete_payload(text: str, diagram_type: str | None) -> dict[str, Any] | None:
    item = _extract_after_delete_word(text)
    if not item:
        return None
    if "关系" in text or "关联" in text:
        payload: dict[str, Any] = {"action": "delete_relation", "relation_text": item}
        endpoints = _relation_endpoints_from_text(item)
        if endpoints:
            payload["source_entity"], payload["target_entity"] = endpoints
        return payload
    if "泳道" in text or diagram_type == "swimlane":
        lane_name = re.sub(r"(泳道)$", "", item).strip(" ，,。；;:：、 ") or item
        return {"action": "delete_swimlane", "lane_name": lane_name}
    if "任务" in text or diagram_type == "gantt":
        task_name = re.sub(r"(任务)$", "", item).strip(" ，,。；;:：、 ") or item
        return {"action": "delete_gantt_task", "task_name": task_name}
    if "节点" in text or "步骤" in text or diagram_type in {"activity", "org"}:
        node_text = re.sub(r"(节点|步骤)$", "", item).strip(" ，,。；;:：、 ") or item
        return {"action": "delete_node", "node_text": node_text}
    return None


def _action_title(payload: dict[str, Any]) -> str:
    action = payload.get("action")
    if action == "rename":
        return f"把 {payload.get('old_text')} 改成 {payload.get('new_text')}"
    if action == "add_gantt_task":
        return f"增加甘特任务 {payload.get('task_name')}"
    if action == "update_gantt_task":
        parts = [f"修改甘特任务 {payload.get('task_name')}"]
        if payload.get("duration_days"):
            parts.append(f"时长为 {payload.get('duration_days')} 天")
        if payload.get("starts_after"):
            parts.append(f"开始依赖 {payload.get('starts_after')}")
        return ", ".join(parts)
    if action == "add_swimlane":
        return f"增加泳道 {payload.get('lane_name')}"
    if action == "add_relation":
        return f"增加关系 {payload.get('relation_text')}"
    if action == "add_node":
        return f"增加节点 {payload.get('node_text')}"
    if action == "delete_node":
        return f"删除节点 {payload.get('node_text')}"
    if action == "delete_gantt_task":
        return f"删除甘特任务 {payload.get('task_name')}"
    if action == "delete_swimlane":
        return f"删除泳道 {payload.get('lane_name')}"
    if action == "delete_relation":
        return f"删除关系 {payload.get('relation_text')}"
    if action == "update_relation":
        return f"修改关系 {payload.get('relation_text')}"
    return "修改 PlantUML 图表"
