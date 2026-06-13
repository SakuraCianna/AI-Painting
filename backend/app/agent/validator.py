from __future__ import annotations

from typing import Any

from .scene_graph import AgentSceneGraph, AgentSceneObject, AgentSceneRelation


ALLOWED_LAYER_IDS = {"background", "base", "middle", "foreground"}
COORDINATE_KEYS = {"x", "y", "cx", "cy", "x1", "y1", "x2", "y2"}
CONTROL_POINT_KEYS = {"x1", "y1", "x2", "y2", "x", "y"}


class SceneGraphValidationError(ValueError):
    pass


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _repair_number(value: Any, minimum: float, maximum: float) -> Any:
    number = _as_number(value)
    if number is None:
        return value
    repaired = _clamp(number, minimum, maximum)
    if isinstance(value, int):
        return int(round(repaired))
    return round(repaired, 2)


def _repair_geometry_value(key: str, value: Any, canvas_width: int, canvas_height: int) -> Any:
    if key in {"x", "cx", "x1", "x2"}:
        return _repair_number(value, 0, canvas_width)
    if key in {"y", "cy", "y1", "y2"}:
        return _repair_number(value, 0, canvas_height)
    if key in {"width", "rx"}:
        return _repair_number(value, 1, canvas_width)
    if key in {"height", "ry"}:
        return _repair_number(value, 1, canvas_height)
    if key in {"radius", "outerRadius", "innerRadius", "size"}:
        return _repair_number(value, 1, max(canvas_width, canvas_height))
    return value


def _repair_geometry(geometry: dict[str, Any], canvas_width: int, canvas_height: int) -> dict[str, Any]:
    repaired: dict[str, Any] = {}
    for key, value in geometry.items():
        if isinstance(value, list):
            repaired[key] = [_repair_geometry(item, canvas_width, canvas_height) if isinstance(item, dict) else item for item in value]
            continue
        if isinstance(value, dict):
            repaired[key] = _repair_geometry(value, canvas_width, canvas_height)
            continue
        repaired[key] = _repair_geometry_value(key, value, canvas_width, canvas_height)
    return repaired


def _repair_object(scene_object: AgentSceneObject, domain: str, canvas_width: int, canvas_height: int) -> AgentSceneObject:
    repaired = scene_object.model_copy(deep=True)
    if repaired.layer_id not in ALLOWED_LAYER_IDS:
        repaired.layer_id = "middle"
    repaired.geometry = _repair_geometry(repaired.geometry, canvas_width, canvas_height)
    tags = list(repaired.semantic_tags)
    if domain and domain not in tags:
        tags.append(domain)
    if repaired.group_id and repaired.group_id not in tags:
        tags.append(repaired.group_id)
    repaired.semantic_tags = tags
    return repaired


def repair_scene_graph(graph: AgentSceneGraph) -> AgentSceneGraph:
    repaired = graph.model_copy(deep=True)
    repaired.objects = [
        _repair_object(scene_object, repaired.domain, repaired.canvas_width, repaired.canvas_height)
        for scene_object in repaired.objects
    ]
    object_ids = {scene_object.object_id for scene_object in repaired.objects}
    repaired.relations = [
        relation
        for relation in repaired.relations
        if relation.subject in object_ids and relation.target in object_ids
    ]
    if repaired.risk_level == "high":
        repaired.requires_confirmation = True
        if not repaired.clarification_question:
            repaired.clarification_question = "这条复杂绘图计划风险较高, 请确认后再执行。"
    return repaired


def validate_scene_graph_for_compilation(graph: AgentSceneGraph, *, max_objects: int = 40) -> AgentSceneGraph:
    if graph.requires_confirmation:
        return graph
    if not graph.objects:
        raise SceneGraphValidationError("SceneGraph 没有对象")
    if len(graph.objects) > max_objects:
        raise SceneGraphValidationError("SceneGraph 对象数量超过限制")
    object_ids = {scene_object.object_id for scene_object in graph.objects}
    for relation in graph.relations:
        if relation.subject not in object_ids or relation.target not in object_ids:
            raise SceneGraphValidationError("SceneGraph 包含无效关系")
    return graph
