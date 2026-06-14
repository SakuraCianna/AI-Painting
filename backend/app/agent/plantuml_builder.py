from __future__ import annotations

import re
from typing import Any

from ..plantuml_renderer import render_plantuml_source
from .scene_graph import AgentSceneGraph, AgentSceneObject, AgentStyle


ER_DEFAULT_ENTITIES = ("用户", "订单", "商品", "支付")
ER_ENTITY_ATTRIBUTES = {
    "用户": ("用户ID", "昵称", "手机号"),
    "订单": ("订单ID", "金额", "状态"),
    "商品": ("商品ID", "名称", "价格"),
    "支付": ("支付ID", "渠道", "时间"),
    "读者": ("读者ID", "姓名", "证件号"),
    "图书": ("图书ID", "书名", "ISBN"),
    "借阅记录": ("借阅ID", "借出时间", "归还状态"),
    "馆员": ("馆员ID", "姓名", "工号"),
}
SWIMLANE_DEFAULT_LANES = ("销售", "运营", "交付")
SWIMLANE_STEP_NAMES = {
    "销售": "线索录入",
    "运营": "资源排期",
    "交付": "交付验收",
    "产品": "需求确认",
    "设计": "方案设计",
    "研发": "开发实现",
    "开发": "开发实现",
    "测试": "测试验收",
}
ORG_CHART_DEFAULT_TOP_ROLE = "负责人"
ORG_CHART_DEFAULT_MIDDLE_ROLES = ("产品组", "设计组", "研发组")
ORG_CHART_DEFAULT_BOTTOM_ROLES = ("用户研究", "交互设计", "前端开发", "后端开发")
ORG_CHART_IGNORED_ROLE_NAMES = {"执行角色", "角色", "岗位", "成员", "团队", "部门", "职能小组"}
GANTT_DEFAULT_TASKS = ("需求梳理", "原型设计", "开发联调", "测试上线")
COMPONENT_DEFAULT_MODULES = ("前端工作台", "FastAPI 后端", "ASR 服务", "Drawing Agent", "SQLite 数据库", "图像生成服务")
COMPACT_PLANTUML_STYLE_LINES = (
    "skinparam shadowing false",
    "skinparam roundcorner 10",
    "skinparam backgroundColor transparent",
    "skinparam defaultFontSize 12",
    "skinparam titleFontSize 16",
    "skinparam ArrowFontSize 11",
)


def build_plantuml_scene_graph(text: str) -> AgentSceneGraph | None:
    normalized_text = text.lower()
    if not any(keyword in text for keyword in ("画", "创建", "生成")):
        return None
    if "泳道图" in text:
        return _plantuml_swimlane_graph(text)
    if any(keyword in text for keyword in ("甘特图", "排期图", "项目排期", "进度计划")):
        return _plantuml_gantt_graph(text)
    if any(keyword in text for keyword in ("组织结构", "组织架构", "团队架构", "团队结构")):
        return _plantuml_org_graph(text)
    if any(keyword in normalized_text for keyword in ("er图", "er 图", "实体关系图", "实体关系")):
        return _plantuml_er_graph(text)
    if any(keyword in normalized_text for keyword in ("系统架构", "技术架构", "应用架构", "架构图", "结构图")) and not any(
        keyword in normalized_text for keyword in ("组织架构", "团队架构", "组织结构")
    ):
        return _plantuml_component_graph(text)
    if any(keyword in text for keyword in ("时序图", "序列图", "调用链")):
        return _plantuml_sequence_graph(text)
    if any(keyword in normalized_text for keyword in ("类图", "uml图", "uml")):
        return _plantuml_class_graph(text)
    if "流程图" in text:
        return _plantuml_activity_graph(text)
    return None


def _plantuml_object(*, title: str, diagram_type: str, source: str, summary: str, tags: list[str]) -> AgentSceneObject:
    result = render_plantuml_source(source)
    x, y, width, height, display_scale = _fit_plantuml_box(result.width, result.height)
    return AgentSceneObject(
        object_id=f"plantuml-{diagram_type}",
        type="plantuml",
        name=title,
        layer_id="middle",
        group_id=f"plantuml-{diagram_type}",
        semantic_tags=["plantuml", f"plantuml.{diagram_type}", *tags],
        geometry={
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "displayScale": display_scale,
            "isDownscaled": display_scale < 1,
            "intrinsicWidth": result.width,
            "intrinsicHeight": result.height,
            "title": title,
            "diagramType": diagram_type,
            "source": source,
            "svg": result.svg,
            "src": result.data_url,
            "renderMode": result.mode,
            "renderError": result.error,
            "summary": summary,
            "preserveAspectRatio": "xMidYMid meet",
        },
        style=AgentStyle(fill="transparent", stroke="#dadce0", strokeWidth=0, opacity=1),
        z_index=10,
        role="plantuml_diagram",
    )


def _fit_plantuml_box(
    intrinsic_width: float,
    intrinsic_height: float,
    *,
    left: float = 48,
    top: float = 48,
    max_width: float = 928,
    max_height: float = 672,
) -> tuple[float, float, float, float, float]:
    if intrinsic_width <= 0 or intrinsic_height <= 0:
        return left, top, max_width, max_height, 1.0
    scale = min(max_width / intrinsic_width, max_height / intrinsic_height, 1.0)
    width = intrinsic_width * scale
    height = intrinsic_height * scale
    x = left + (max_width - width) / 2
    y = top + (max_height - height) / 2
    return round(x, 2), round(y, 2), round(width, 2), round(height, 2), round(scale, 2)


def _compact_plantuml_style_lines(*extra_lines: str) -> list[str]:
    return [*COMPACT_PLANTUML_STYLE_LINES, *extra_lines]


def _plantuml_graph(*, title: str, diagram_type: str, source: str, summary: str, tags: list[str]) -> AgentSceneGraph:
    return AgentSceneGraph(
        intent=f"compose_plantuml_{diagram_type}",
        domain=f"plantuml_{diagram_type}_scene",
        summary=summary,
        background="#ffffff",
        objects=[_plantuml_object(title=title, diagram_type=diagram_type, source=source, summary=summary, tags=tags)],
        relations=[],
        confidence=0.86,
    )


def _clean_token(value: str) -> str:
    return value.strip(" ，,。；;:：、 \t\n\r")


def _safe_alias(name: str, index: int) -> str:
    ascii_alias = re.sub(r"[^0-9a-zA-Z_]+", "_", name).strip("_")
    return ascii_alias or f"entity_{index + 1}"


def _extract_title(text: str, markers: tuple[str, ...], fallback: str) -> str:
    for marker in markers:
        marker_index = text.find(marker)
        if marker_index < 0:
            continue
        title = text[:marker_index]
        for prefix in ("画一个", "创建一个", "生成一个", "画", "创建", "生成"):
            if title.startswith(prefix):
                title = title[len(prefix) :]
                break
        title = _clean_token(title)
        if title:
            return f"{title}{marker.upper() if marker.lower() == 'er图' else marker}"
    return fallback


def _extract_er_entity_names(text: str) -> list[str]:
    match = re.search(r"(?:实体|数据表|表|包含)\s*(?:包括|包含|有)?(.+?)(?:关系\s*(?:包括|包含|有)|。|$)", text)
    if not match:
        return list(ER_DEFAULT_ENTITIES)
    raw_text = match.group(1)
    names: list[str] = []
    for raw_name in re.split(r"[、,，;；和]+", raw_text):
        name = _clean_token(raw_name)
        if not name or "er" in name.lower() or name in names:
            continue
        names.append(name)
        if len(names) == 6:
            break
    return names or list(ER_DEFAULT_ENTITIES)


def _relationship_cardinality(name: str) -> str:
    if "支付" in name:
        return "||--||"
    if any(keyword in name for keyword in ("包含", "借阅", "拥有", "选择")):
        return "||--o{"
    return "||--o{"


def _infer_relationship_endpoints(relationship_name: str, entity_names: list[str], fallback_index: int) -> tuple[int, int]:
    matched = sorted(
        ((index, relationship_name.find(entity_name)) for index, entity_name in enumerate(entity_names) if entity_name in relationship_name),
        key=lambda item: item[1],
    )
    if len(matched) >= 2:
        return matched[0][0], matched[1][0]
    source = min(fallback_index, max(len(entity_names) - 2, 0))
    return source, min(source + 1, len(entity_names) - 1)


def _extract_er_relationships(text: str, entity_names: list[str]) -> list[dict[str, Any]]:
    match = re.search(r"(?:关系|关联)\s*(?:包括|包含|有)(.+?)(?:[。]|$)", text)
    relationship_names = [_clean_token(name) for name in re.split(r"[、,，;；]+", match.group(1))] if match else []
    relationships: list[dict[str, Any]] = []
    for raw_name in relationship_names:
        if not raw_name:
            continue
        source_index, target_index = _infer_relationship_endpoints(raw_name, entity_names, len(relationships))
        if source_index != target_index:
            relationships.append({"name": raw_name, "source_index": source_index, "target_index": target_index})
        if len(relationships) == 5:
            return relationships
    defaults = [(0, 1, "创建"), (1, 2, "包含"), (1, 3, "产生"), (0, 2, "浏览")]
    for source_index, target_index, name in defaults:
        if len(relationships) == 5 or target_index >= len(entity_names):
            break
        relationships.append({"name": name, "source_index": source_index, "target_index": target_index})
    return relationships


def _split_short_chinese_list(raw_items: str, *, max_items: int) -> list[str]:
    items: list[str] = []
    for raw_item in re.split(r"[、,，/和与及]+", raw_items):
        item = raw_item.strip(" 。；;:：")
        item = re.sub(r"^(分别是|分别为|包括|包含|有|为|是)", "", item).strip(" 。；;:：")
        item = re.sub(r"(泳道|部门|角色|节点|步骤|任务|里程碑|这些|等等|等)$", "", item).strip(" 。；;:：")
        if 1 <= len(item) <= 12 and item not in items:
            items.append(item)
    return items[:max_items]


def _split_org_chart_role_list(raw_items: str, *, max_items: int) -> list[str]:
    items = []
    for item in _split_short_chinese_list(raw_items, max_items=max_items):
        if item not in ORG_CHART_IGNORED_ROLE_NAMES:
            items.append(item)
    return items[:max_items]


def _fill_roles(custom_names: list[str], defaults: tuple[str, ...], *, target_count: int) -> list[str]:
    roles = list(custom_names[:target_count])
    for default_name in defaults:
        if len(roles) >= target_count:
            break
        if default_name not in roles:
            roles.append(default_name)
    return roles[:target_count]


def _extract_org_chart_roles(text: str) -> tuple[str, list[str], list[str]]:
    match = re.search(
        r"(?:组织结构图|组织架构图|团队架构图|团队结构图|组织结构|组织架构|团队架构|团队结构)(?:，|,)?(?:包括|包含|有|为|是)([^。；;]+)",
        text,
    )
    role_names = _split_org_chart_role_list(match.group(1), max_items=8) if match else []
    if not role_names:
        return ORG_CHART_DEFAULT_TOP_ROLE, list(ORG_CHART_DEFAULT_MIDDLE_ROLES), list(ORG_CHART_DEFAULT_BOTTOM_ROLES)
    top_role = role_names[0]
    middle_roles = _fill_roles(role_names[1:4], ORG_CHART_DEFAULT_MIDDLE_ROLES, target_count=3)
    bottom_roles = _fill_roles(role_names[4:8], ORG_CHART_DEFAULT_BOTTOM_ROLES, target_count=4)
    return top_role, middle_roles, bottom_roles


def _extract_swimlane_names(text: str) -> list[str]:
    match = re.search(r"(?:泳道(?:包括|包含|有|为|是)|包括|包含|有)([^。,.，；;]+)", text)
    if match is None:
        return list(SWIMLANE_DEFAULT_LANES)
    names = _split_short_chinese_list(match.group(1), max_items=4)
    return names if len(names) >= 2 else list(SWIMLANE_DEFAULT_LANES)


def _extract_swimlane_step_names(text: str) -> list[str]:
    match = re.search(r"(?:流程节点|流程步骤|节点|步骤)(?:包括|包含|有|为|是)([^。,.，；;]+)", text)
    if match is None:
        return []
    return _split_short_chinese_list(match.group(1), max_items=4)


def _swimlane_step_name(lane_name: str, index: int) -> str:
    if lane_name == "销售" and index == 1:
        return "方案确认"
    return SWIMLANE_STEP_NAMES.get(lane_name, f"{lane_name}处理")


def _extract_gantt_task_names(text: str) -> list[str]:
    match = re.search(r"(?:包含|包括|有)([^。；;]+)", text)
    if match is None:
        return list(GANTT_DEFAULT_TASKS)
    tasks = _split_short_chinese_list(match.group(1), max_items=5)
    cleaned = [task for task in tasks if "上线" not in task and "里程碑" not in task]
    return cleaned[:4] or list(GANTT_DEFAULT_TASKS)


def _extract_component_names(text: str) -> list[str]:
    match = re.search(r"(?:包含|包括|有)([^。；;]+)", text)
    if match is None:
        return list(COMPONENT_DEFAULT_MODULES)
    names = [name for name in _split_short_chinese_list(match.group(1), max_items=10) if name not in {"模块", "组件", "系统", "服务", "架构"}]
    return names if len(names) >= 3 else list(COMPONENT_DEFAULT_MODULES)


def _component_declaration(name: str, alias: str, index: int) -> str:
    palette = ("#E8F0FE", "#E6F4EA", "#FEF7E0", "#FCE8E6", "#F1F3F4")
    color = palette[index % len(palette)]
    if any(keyword in name.lower() for keyword in ("db", "sql", "sqlite", "mysql", "postgres", "redis")) or "数据库" in name:
        return f'database "{name}" as {alias} {color}'
    if any(keyword in name.lower() for keyword in ("mq", "kafka", "rabbitmq")) or "队列" in name or "消息" in name:
        return f'queue "{name}" as {alias} {color}'
    return f'component "{name}" as {alias} {color}'


def _plantuml_er_graph(text: str) -> AgentSceneGraph:
    title = _extract_title(text, ("er图", "er 图", "实体关系图"), "实体关系图")
    entity_names = _extract_er_entity_names(text)
    relationships = _extract_er_relationships(text, entity_names)
    aliases = [_safe_alias(name, index) for index, name in enumerate(entity_names)]
    lines = [
        "@startuml",
        "' AI Painting generated PlantUML ER diagram",
        *_compact_plantuml_style_lines(
            "skinparam linetype ortho",
            "skinparam classFontSize 12",
            "skinparam classAttributeFontSize 11",
            "skinparam classBackgroundColor #F8FAFC",
            "skinparam classBorderColor #5F6368",
            "skinparam classFontColor #202124",
        ),
        "skinparam entity {",
        "  BackgroundColor #F8FAFC",
        "  BorderColor #5F6368",
        "  FontColor #202124",
        "}",
        f"title {title}",
    ]
    for index, name in enumerate(entity_names):
        alias = aliases[index]
        lines.append(f'entity "{name}" as {alias} {{')
        for attribute in ER_ENTITY_ATTRIBUTES.get(name, ("ID", "名称", "状态")):
            prefix = "*" if attribute.endswith("ID") or attribute == "ID" else "--"
            lines.append(f"  {prefix} {attribute}")
        lines.append("}")
    for relationship in relationships:
        source = aliases[relationship["source_index"]]
        target = aliases[relationship["target_index"]]
        relation = _relationship_cardinality(relationship["name"])
        lines.append(f"{source} {relation} {target} : {relationship['name']}")
    lines.append("@enduml")
    relationship_summary = "、".join(str(relationship["name"]) for relationship in relationships)
    summary = f"使用 PlantUML 绘制{title}, 包含{'、'.join(entity_names)}实体, 关系包括{relationship_summary}"
    return _plantuml_graph(title=title, diagram_type="er", source="\n".join(lines), summary=summary, tags=["er_diagram"])


def _plantuml_org_graph(text: str) -> AgentSceneGraph:
    title = "产品团队组织结构图" if "产品" in text else "团队组织结构图"
    top_role, middle_roles, bottom_roles = _extract_org_chart_roles(text)
    lines = [
        "@startwbs",
        "' AI Painting generated PlantUML organization chart",
        *_compact_plantuml_style_lines(),
        f"title {title}",
        f"* {title}",
        f"** {top_role}",
    ]
    role_index = 0
    for middle_role in middle_roles:
        lines.append(f"*** {middle_role}")
        assigned_roles = bottom_roles[role_index : role_index + 2]
        if not assigned_roles:
            assigned_roles = bottom_roles[-1:]
        for bottom_role in assigned_roles:
            lines.append(f"**** {bottom_role}")
        role_index += 2
    lines.append("@endwbs")
    summary = f"使用 PlantUML 绘制组织结构图, 包含{top_role}、{'、'.join(middle_roles)}和{'、'.join(bottom_roles)}"
    return _plantuml_graph(title=title, diagram_type="org", source="\n".join(lines), summary=summary, tags=["org_chart"])


def _plantuml_gantt_graph(text: str) -> AgentSceneGraph:
    title = "产品迭代甘特图" if "产品" in text else "项目排期甘特图"
    task_names = _extract_gantt_task_names(text)
    while len(task_names) < 4:
        task_names.append(GANTT_DEFAULT_TASKS[len(task_names)])
    task_names = task_names[:4]
    durations = (7, 10, 14, 7)
    colors = ("#1A73E8", "#34A853", "#FBBC04", "#EA4335")
    lines = [
        "@startgantt",
        "' AI Painting generated PlantUML Gantt chart",
        *_compact_plantuml_style_lines(),
        f"title {title}",
        "printscale weekly",
        "project starts 2026-01-01",
    ]
    previous_task = ""
    for index, task_name in enumerate(task_names):
        safe_task = task_name.replace("]", "")
        if index == 0:
            lines.append(f"[{safe_task}] lasts {durations[index]} days")
        else:
            lines.append(f"[{safe_task}] starts at [{previous_task}]'s end")
            lines.append(f"[{safe_task}] lasts {durations[index]} days")
        lines.append(f"[{safe_task}] is colored in {colors[index]}")
        previous_task = safe_task
    lines.append(f"[上线里程碑] happens at [{previous_task}]'s end")
    lines.append("@endgantt")
    summary = f"使用 PlantUML 绘制甘特图, 任务包括{'、'.join(task_names)}和上线里程碑"
    return _plantuml_graph(title=title, diagram_type="gantt", source="\n".join(lines), summary=summary, tags=["gantt_chart"])


def _plantuml_swimlane_graph(text: str) -> AgentSceneGraph:
    lane_names = _extract_swimlane_names(text)
    custom_step_names = _extract_swimlane_step_names(text)
    steps: list[tuple[str, str]] = []
    for index in range(4):
        lane_name = lane_names[min(index, len(lane_names) - 1)] if len(lane_names) <= 2 else lane_names[index % len(lane_names)]
        step_name = custom_step_names[index] if index < len(custom_step_names) else _swimlane_step_name(lane_name, index)
        steps.append((lane_name, step_name))
    title = "跨职能泳道图"
    lines = [
        "@startuml",
        "' AI Painting generated PlantUML swimlane activity diagram",
        *_compact_plantuml_style_lines(
            "skinparam activityFontSize 12",
            "skinparam ActivityBackgroundColor #E8F0FE",
            "skinparam ActivityBorderColor #5F6368",
        ),
        f"title {title}",
        "start",
    ]
    for lane_name, step_name in steps:
        lines.append(f"|{lane_name}|")
        lines.append(f":{step_name};")
    lines.extend(["stop", "@enduml"])
    lane_summary = "、".join(lane_names)
    step_summary = "、".join(step_name for _, step_name in steps)
    summary = f"使用 PlantUML 绘制{lane_summary}泳道图, 节点包括{step_summary}"
    return _plantuml_graph(title=title, diagram_type="swimlane", source="\n".join(lines), summary=summary, tags=["swimlane_diagram"])


def _plantuml_component_graph(text: str) -> AgentSceneGraph:
    title = "AI 绘图系统架构" if "ai" in text or "绘图" in text else "系统架构图"
    module_names = _extract_component_names(text)
    aliases = [_safe_alias(name, index) for index, name in enumerate(module_names)]
    declaration_lines = [_component_declaration(name, aliases[index], index) for index, name in enumerate(module_names)]
    relation_lines: list[str] = []
    if len(aliases) >= 2:
        relation_lines.append(f"{aliases[0]} --> {aliases[1]} : 入口请求")
        hub = aliases[1]
        for index, alias in enumerate(aliases[2:], start=2):
            label = "写入" if "数据库" in module_names[index] else "投递" if "队列" in module_names[index] or "消息" in module_names[index] else "调用"
            relation_lines.append(f"{hub} --> {alias} : {label}")
    lines = [
        "@startuml",
        "' AI Painting generated PlantUML component diagram",
        *_compact_plantuml_style_lines(
            "skinparam componentStyle rectangle",
            "skinparam componentFontSize 12",
            "skinparam databaseFontSize 12",
            "skinparam componentBorderColor #5F6368",
            "skinparam databaseBorderColor #5F6368",
        ),
        f"title {title}",
        *declaration_lines,
        *relation_lines,
        "@enduml",
    ]
    summary = f"使用 PlantUML 绘制系统架构图, 展示{'、'.join(module_names)}"
    return _plantuml_graph(title=title, diagram_type="component", source="\n".join(lines), summary=summary, tags=["system_architecture"])


def _plantuml_activity_graph(text: str) -> AgentSceneGraph:
    labels = ["用户语音", "ASR 识别", "意图分类", "任务规划", "画布执行"]
    if "导出" in text:
        labels.append("导出结果")
    lines = [
        "@startuml",
        "' AI Painting generated PlantUML activity diagram",
        *_compact_plantuml_style_lines(
            "skinparam activityFontSize 12",
            "skinparam ActivityBackgroundColor #E8F0FE",
            "skinparam ActivityBorderColor #5F6368",
        ),
        "title 语音绘图流程图",
        "start",
    ]
    lines.extend(f":{label};" for label in labels)
    lines.extend(["stop", "@enduml"])
    summary = "使用 PlantUML 绘制从用户语音到画布执行的流程图"
    return _plantuml_graph(title="语音绘图流程图", diagram_type="activity", source="\n".join(lines), summary=summary, tags=["flowchart"])


def _plantuml_sequence_graph(text: str) -> AgentSceneGraph:
    lines = [
        "@startuml",
        *_compact_plantuml_style_lines(
            "skinparam sequenceParticipantFontSize 12",
            "skinparam sequenceMessageFontSize 11",
        ),
        "title 语音绘图调用时序图",
        "actor 用户",
        "participant 前端",
        "participant ASR",
        "participant 后端",
        "participant DrawingAgent",
        "database SQLite",
        "用户 -> 前端 : 语音输入",
        "前端 -> ASR : 音频转写",
        "ASR --> 前端 : 文本",
        "前端 -> 后端 : 提交指令",
        "后端 -> DrawingAgent : 生成计划",
        "DrawingAgent -> SQLite : 读取上下文",
        "DrawingAgent --> 后端 : 操作计划",
        "后端 -> SQLite : 写入对象和历史",
        "后端 --> 前端 : 返回画布",
        "@enduml",
    ]
    summary = "使用 PlantUML 绘制语音绘图调用时序图"
    return _plantuml_graph(title="语音绘图调用时序图", diagram_type="sequence", source="\n".join(lines), summary=summary, tags=["sequence_diagram"])


def _plantuml_class_graph(text: str) -> AgentSceneGraph:
    lines = [
        "@startuml",
        *_compact_plantuml_style_lines(
            "skinparam classFontSize 12",
            "skinparam classAttributeFontSize 11",
            "skinparam classBackgroundColor #F8FAFC",
            "skinparam classBorderColor #5F6368",
        ),
        "title 绘图 Agent 类图",
        "class Artwork {",
        "  +id",
        "  +title",
        "  +objects",
        "}",
        "class DrawingObject {",
        "  +type",
        "  +geometry",
        "  +style",
        "  +semantic_tags",
        "}",
        "class CommandPlan {",
        "  +operations",
        "  +scene_plan",
        "  +confidence",
        "}",
        "class DrawingAgent {",
        "  +classify()",
        "  +plan()",
        "  +execute()",
        "}",
        'Artwork "1" o-- "many" DrawingObject',
        "DrawingAgent --> CommandPlan",
        "CommandPlan --> DrawingObject",
        "@enduml",
    ]
    summary = "使用 PlantUML 绘制绘图 Agent 类图"
    return _plantuml_graph(title="绘图 Agent 类图", diagram_type="class", source="\n".join(lines), summary=summary, tags=["uml_class"])
