from __future__ import annotations

import re
from typing import Any

from .plantuml_renderer import render_plantuml_source


class PlantUMLEditError(ValueError):
    pass


def edit_plantuml_geometry(geometry: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    source = str(geometry.get("source") or "").strip()
    if not source:
        raise PlantUMLEditError("PlantUML 对象缺少源码")

    action = str(payload.get("action") or "").strip()
    if action == "rename":
        next_source = _rename_text(source, str(payload.get("old_text") or ""), str(payload.get("new_text") or ""))
    elif action == "add_node":
        next_source = _add_activity_node(source, str(payload.get("node_text") or ""))
    elif action == "add_gantt_task":
        next_source = _add_gantt_task(source, str(payload.get("task_name") or ""))
    elif action == "add_swimlane":
        next_source = _add_swimlane(source, str(payload.get("lane_name") or ""), str(payload.get("step_name") or ""))
    elif action == "add_relation":
        next_source = _add_relation(source, str(payload.get("relation_text") or ""))
    else:
        raise PlantUMLEditError(f"不支持的 PlantUML 编辑动作: {action}")

    result = render_plantuml_source(next_source)
    updated = dict(geometry)
    updated.update(
        {
            "source": next_source,
            "svg": result.svg,
            "src": result.data_url,
            "renderMode": result.mode,
            "renderError": result.error,
        }
    )
    return updated


def _safe_label(value: str, *, max_length: int = 60) -> str:
    label = value.strip(" ，,。；;:：、 \t\n\r")
    label = re.sub(r"\s+", " ", label)
    label = re.sub(r"[@!{}\[\]\"<>]", "", label)
    label = label.replace("|", "").replace(";", "")
    if not label:
        raise PlantUMLEditError("PlantUML 编辑内容不能为空")
    return label[:max_length]


def _flexible_text_pattern(value: str) -> re.Pattern[str]:
    compact = re.sub(r"\s+", "", value.strip())
    if not compact:
        raise PlantUMLEditError("需要提供要修改的原文本")
    parts = [re.escape(char) for char in compact]
    return re.compile(r"\s*".join(parts), re.IGNORECASE)


def _rename_text(source: str, old_text: str, new_text: str) -> str:
    old_label = _safe_label(old_text)
    new_label = _safe_label(new_text)
    if old_label in source:
        return source.replace(old_label, new_label, 1)
    pattern = _flexible_text_pattern(old_label)
    next_source, count = pattern.subn(new_label, source, count=1)
    if count == 0:
        raise PlantUMLEditError(f"没有找到 PlantUML 文本: {old_label}")
    return next_source


def _insert_before_line(source: str, marker_pattern: str, inserted_lines: list[str]) -> str:
    lines = source.splitlines()
    marker = re.compile(marker_pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        if marker.fullmatch(line.strip()):
            return "\n".join([*lines[:index], *inserted_lines, *lines[index:]])
    raise PlantUMLEditError("没有找到可插入位置")


def _add_activity_node(source: str, node_text: str) -> str:
    node = _safe_label(node_text)
    if f":{node};" in source:
        raise PlantUMLEditError(f"PlantUML 节点已存在: {node}")
    if re.search(r"^\s*stop\s*$", source, re.IGNORECASE | re.MULTILINE):
        return _insert_before_line(source, r"stop", [f":{node};"])
    if re.search(r"^\s*@endwbs\s*$", source, re.IGNORECASE | re.MULTILINE):
        return _insert_before_line(source, r"@endwbs", [f"*** {node}"])
    raise PlantUMLEditError("当前 PlantUML 图不支持新增节点")


def _last_gantt_task_name(source: str) -> str | None:
    task_names = re.findall(r"^\s*\[([^\]]+)\]\s+lasts\s+\d+\s+days\s*$", source, re.MULTILINE)
    return task_names[-1] if task_names else None


def _add_gantt_task(source: str, task_name: str) -> str:
    task = _safe_label(task_name, max_length=32)
    if f"[{task}]" in source:
        raise PlantUMLEditError(f"PlantUML 任务已存在: {task}")
    milestone_pattern = re.compile(r"^\s*\[上线里程碑\]\s+happens at \[([^\]]+)\]'s end\s*$", re.MULTILINE)
    milestone_match = milestone_pattern.search(source)
    previous_task = milestone_match.group(1) if milestone_match else _last_gantt_task_name(source)
    if not previous_task:
        raise PlantUMLEditError("没有找到可衔接的甘特图任务")
    task_lines = [
        f"[{task}] starts at [{previous_task}]'s end",
        f"[{task}] lasts 5 days",
        f"[{task}] is colored in #A142F4",
    ]
    if milestone_match:
        before = source[: milestone_match.start()].rstrip("\n")
        after = source[milestone_match.end() :].lstrip("\n")
        milestone_line = f"[上线里程碑] happens at [{task}]'s end"
        return "\n".join([before, *task_lines, milestone_line, after]).strip()
    return _insert_before_line(source, r"@endgantt", task_lines)


def _add_swimlane(source: str, lane_name: str, step_name: str) -> str:
    lane = _safe_label(lane_name, max_length=24)
    step = _safe_label(step_name or f"{lane}处理", max_length=32)
    if f"|{lane}|" in source:
        raise PlantUMLEditError(f"PlantUML 泳道已存在: {lane}")
    return _insert_before_line(source, r"stop", [f"|{lane}|", f":{step};"])


def _named_aliases(source: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in re.finditer(r'\b(?:entity|component|database)\s+"([^"]+)"\s+as\s+([A-Za-z0-9_]+)', source):
        display_name = match.group(1).split("\\n", 1)[0].strip()
        aliases[display_name] = match.group(2)
    return aliases


def _relation_from_text(source: str, relation_text: str) -> tuple[str, str, str]:
    relation = _safe_label(relation_text, max_length=80)
    aliases = _named_aliases(source)
    matched_names = sorted(
        (name for name in aliases if name and name in relation),
        key=lambda name: relation.find(name),
    )
    if len(matched_names) < 2:
        raise PlantUMLEditError("新增关系需要同时说出两个已有实体或模块名称")
    source_name, target_name = matched_names[0], matched_names[1]
    label = relation.replace(source_name, "", 1).replace(target_name, "", 1).strip(" 的之和与关联关系")
    if not label:
        label = "关联"
    return aliases[source_name], aliases[target_name], _safe_label(label, max_length=30)


def _add_relation(source: str, relation_text: str) -> str:
    source_alias, target_alias, label = _relation_from_text(source, relation_text)
    line = f"{source_alias} ||--o{{ {target_alias} : {label}"
    if line in source:
        raise PlantUMLEditError(f"PlantUML 关系已存在: {label}")
    return _insert_before_line(source, r"@enduml", [line])
