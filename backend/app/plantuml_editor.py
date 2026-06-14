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
    elif action == "update_gantt_task":
        next_source = _update_gantt_task(
            source,
            str(payload.get("task_name") or ""),
            payload.get("duration_days"),
            str(payload.get("starts_after") or ""),
        )
    elif action == "add_swimlane":
        next_source = _add_swimlane(source, str(payload.get("lane_name") or ""), str(payload.get("step_name") or ""))
    elif action == "add_relation":
        next_source = _add_relation(source, str(payload.get("relation_text") or ""))
    elif action == "delete_node":
        next_source = _delete_node(source, str(payload.get("node_text") or ""))
    elif action == "delete_gantt_task":
        next_source = _delete_gantt_task(source, str(payload.get("task_name") or ""))
    elif action == "delete_swimlane":
        next_source = _delete_swimlane(source, str(payload.get("lane_name") or ""))
    elif action == "delete_relation":
        next_source = _delete_relation(
            source,
            str(payload.get("relation_text") or ""),
            str(payload.get("source_entity") or ""),
            str(payload.get("target_entity") or ""),
        )
    elif action == "update_relation":
        next_source = _update_relation(
            source,
            str(payload.get("relation_text") or ""),
            str(payload.get("new_label") or ""),
            str(payload.get("cardinality") or ""),
            str(payload.get("source_entity") or ""),
            str(payload.get("target_entity") or ""),
        )
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


def _compact_label(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _label_matches(candidate: str, expected: str) -> bool:
    compact_candidate = _compact_label(candidate)
    compact_expected = _compact_label(expected)
    return bool(compact_candidate and compact_expected and (compact_candidate == compact_expected or compact_expected in compact_candidate))


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


def _aliases_for_entities(source: str, source_entity: str, target_entity: str) -> tuple[str, str] | None:
    if not source_entity.strip() or not target_entity.strip():
        return None
    aliases = _named_aliases(source)
    source_label = _safe_label(source_entity)
    target_label = _safe_label(target_entity)
    matched_source = next((alias for name, alias in aliases.items() if _label_matches(name, source_label)), None)
    matched_target = next((alias for name, alias in aliases.items() if _label_matches(name, target_label)), None)
    if matched_source is None or matched_target is None:
        raise PlantUMLEditError(f"没有找到 PlantUML 关系端点: {source_label} / {target_label}")
    return matched_source, matched_target


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


def _delete_node(source: str, node_text: str) -> str:
    node = _safe_label(node_text)
    lines = source.splitlines()
    removed = False
    output: list[str] = []
    skip_wbs_depth: int | None = None
    for line in lines:
        stripped = line.strip()
        wbs_match = re.match(r"^(\*+)\s+(.+)$", stripped)
        if skip_wbs_depth is not None:
            if wbs_match and len(wbs_match.group(1)) > skip_wbs_depth:
                continue
            skip_wbs_depth = None
        activity_match = re.match(r"^:(.+);\s*$", stripped)
        if activity_match and _label_matches(activity_match.group(1), node):
            removed = True
            continue
        if wbs_match and _label_matches(wbs_match.group(2), node):
            removed = True
            skip_wbs_depth = len(wbs_match.group(1))
            continue
        output.append(line)
    if not removed:
        raise PlantUMLEditError(f"没有找到 PlantUML 节点: {node}")
    return "\n".join(output)


def _gantt_task_names(source: str) -> list[str]:
    return re.findall(r"^\s*\[([^\]]+)\]\s+lasts\s+\d+\s+days\s*$", source, re.MULTILINE)


def _matching_task_name(source: str, task_name: str) -> str:
    task = _safe_label(task_name, max_length=32)
    for name in _gantt_task_names(source):
        if _label_matches(name, task):
            return name
    raise PlantUMLEditError(f"没有找到 PlantUML 甘特任务: {task}")


def _delete_gantt_task(source: str, task_name: str) -> str:
    task = _matching_task_name(source, task_name)
    sequence = _gantt_task_names(source)
    task_index = sequence.index(task)
    previous_task = sequence[task_index - 1] if task_index > 0 else None
    next_task = sequence[task_index + 1] if task_index + 1 < len(sequence) else None
    if previous_task is None and next_task is None:
        raise PlantUMLEditError("甘特图至少需要保留一个任务")

    output: list[str] = []
    removed = False
    for line in source.splitlines():
        stripped = line.strip()
        if re.match(rf"^\[{re.escape(task)}\]\s+", stripped):
            removed = True
            continue
        if next_task:
            next_start_pattern = rf"^\[{re.escape(next_task)}\]\s+starts at \[{re.escape(task)}\]'s end\s*$"
            if re.match(next_start_pattern, stripped):
                if previous_task:
                    output.append(f"[{next_task}] starts at [{previous_task}]'s end")
                continue
        milestone_match = re.match(rf"^\[上线里程碑\]\s+happens at \[{re.escape(task)}\]'s end\s*$", stripped)
        if milestone_match:
            if previous_task:
                output.append(f"[上线里程碑] happens at [{previous_task}]'s end")
            elif next_task:
                output.append(f"[上线里程碑] happens at [{next_task}]'s end")
            continue
        output.append(line)
    if not removed:
        raise PlantUMLEditError(f"没有找到 PlantUML 甘特任务: {task}")
    return "\n".join(output)


def _normalized_duration_days(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PlantUMLEditError("甘特任务时长必须是数字")
    if isinstance(value, int):
        days = value
    elif isinstance(value, str):
        try:
            days = int(value)
        except ValueError as exc:
            raise PlantUMLEditError("甘特任务时长必须是数字") from exc
    else:
        raise PlantUMLEditError("甘特任务时长必须是数字")
    if days < 1 or days > 365:
        raise PlantUMLEditError("甘特任务时长必须在 1 到 365 天之间")
    return days


def _update_gantt_task(source: str, task_name: str, duration_days: object, starts_after: str) -> str:
    task = _matching_task_name(source, task_name)
    days = _normalized_duration_days(duration_days)
    dependency = _matching_task_name(source, starts_after) if starts_after.strip() else None
    if days is None and dependency is None:
        raise PlantUMLEditError("修改甘特任务需要提供时长或开始依赖")
    if dependency == task:
        raise PlantUMLEditError("甘特任务不能依赖自身开始")

    output: list[str] = []
    updated_duration = days is None
    updated_dependency = dependency is None
    for line in source.splitlines():
        stripped = line.strip()
        duration_match = re.match(rf"^\[{re.escape(task)}\]\s+lasts\s+\d+\s+days\s*$", stripped)
        if duration_match:
            if dependency is not None and not updated_dependency:
                output.append(f"[{task}] starts at [{dependency}]'s end")
                updated_dependency = True
            output.append(f"[{task}] lasts {days} days" if days is not None else line)
            updated_duration = True
            continue
        dependency_match = re.match(rf"^\[{re.escape(task)}\]\s+starts at \[[^\]]+\]'s end\s*$", stripped)
        if dependency_match:
            if dependency is not None:
                output.append(f"[{task}] starts at [{dependency}]'s end")
                updated_dependency = True
            continue
        output.append(line)

    if not updated_duration:
        raise PlantUMLEditError(f"没有找到 PlantUML 甘特任务时长: {task}")
    if not updated_dependency:
        raise PlantUMLEditError(f"没有找到 PlantUML 甘特任务开始位置: {task}")
    return "\n".join(output)


def _delete_swimlane(source: str, lane_name: str) -> str:
    lane = _safe_label(lane_name, max_length=24)
    lines = source.splitlines()
    output: list[str] = []
    removed = False
    skipping_lane = False
    for line in lines:
        stripped = line.strip()
        lane_match = re.match(r"^\|(.+)\|$", stripped)
        if lane_match:
            if _label_matches(lane_match.group(1), lane):
                removed = True
                skipping_lane = True
                continue
            skipping_lane = False
        elif skipping_lane and (stripped.lower() in {"stop", "@enduml"} or stripped.startswith("|")):
            skipping_lane = False
        if skipping_lane:
            continue
        output.append(line)
    if not removed:
        raise PlantUMLEditError(f"没有找到 PlantUML 泳道: {lane}")
    return "\n".join(output)


def _relation_line_pattern() -> re.Pattern[str]:
    return re.compile(
        r"^\s*(?P<source>[A-Za-z0-9_]+)\s+"
        r"(?P<operator>[|}{o*]+--[|}{o*]+)\s+"
        r"(?P<target>[A-Za-z0-9_]+)\s*:\s*"
        r"(?P<label>.+?)\s*$"
    )


def _relation_operator_for_cardinality(cardinality: str) -> str | None:
    normalized = cardinality.strip().lower()
    mapping = {
        "one_to_one": "||--||",
        "one_to_many": "||--o{",
        "many_to_one": "}o--||",
        "many_to_many": "}o--o{",
    }
    return mapping.get(normalized)


def _relation_matches(match: re.Match[str], relation: str, endpoint_aliases: tuple[str, str] | None) -> bool:
    if endpoint_aliases is not None:
        expected = set(endpoint_aliases)
        actual = {match.group("source"), match.group("target")}
        return actual == expected
    return _label_matches(match.group("label"), relation)


def _delete_relation(source: str, relation_text: str, source_entity: str = "", target_entity: str = "") -> str:
    relation = _safe_label(relation_text, max_length=80)
    endpoint_aliases = _aliases_for_entities(source, source_entity, target_entity)
    pattern = _relation_line_pattern()
    output: list[str] = []
    removed = False
    for line in source.splitlines():
        match = pattern.match(line)
        if match and _relation_matches(match, relation, endpoint_aliases):
            removed = True
            continue
        output.append(line)
    if not removed:
        raise PlantUMLEditError(f"没有找到 PlantUML 关系: {relation}")
    return "\n".join(output)


def _update_relation(
    source: str,
    relation_text: str,
    new_label: str,
    cardinality: str,
    source_entity: str = "",
    target_entity: str = "",
) -> str:
    relation = _safe_label(relation_text, max_length=80)
    label = _safe_label(new_label, max_length=30) if new_label.strip() else None
    operator = _relation_operator_for_cardinality(cardinality)
    if label is None and operator is None:
        raise PlantUMLEditError("修改关系需要提供新标签或新基数")
    pattern = _relation_line_pattern()
    endpoint_aliases = _aliases_for_entities(source, source_entity, target_entity)
    output: list[str] = []
    updated = False
    for line in source.splitlines():
        match = pattern.match(line)
        if not match or not _relation_matches(match, relation, endpoint_aliases):
            output.append(line)
            continue
        next_operator = operator or match.group("operator")
        next_label = label or match.group("label")
        output.append(f"{match.group('source')} {next_operator} {match.group('target')} : {next_label}")
        updated = True
    if not updated:
        raise PlantUMLEditError(f"没有找到 PlantUML 关系: {relation}")
    return "\n".join(output)
