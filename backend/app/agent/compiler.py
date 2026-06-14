from __future__ import annotations

from typing import Any

from ..schemas import CommandPlan, OperationRequest, ScenePlan, ScenePlanStep
from .scene_graph import AgentSceneGraph, AgentSceneObject


ALLOWED_OPERATION_TYPES = {
    "create_canvas",
    "add_object",
    "set_style",
    "set_style_many",
    "set_metadata",
    "set_metadata_many",
    "move_object",
    "move_many",
    "scale_object",
    "scale_many",
    "replace_shape",
    "replace_shape_many",
    "generate_image_asset",
    "polish_image_asset",
    "delete_object",
    "clear_canvas",
    "save_artwork",
    "export_artwork",
    "undo",
    "redo",
}
ALLOWED_OBJECT_TYPES = {"rect", "circle", "ellipse", "triangle", "line", "arrow", "star", "text", "polygon", "path", "bezier", "image", "plantuml"}


class SceneGraphCompileError(ValueError):
    pass


def _shape_tag(object_type: str) -> str:
    return f"shape.{object_type}"


def _to_drawing_object(scene_object: AgentSceneObject, index: int) -> dict[str, Any]:
    if scene_object.type not in ALLOWED_OBJECT_TYPES:
        raise SceneGraphCompileError(f"不支持的对象类型: {scene_object.type}")
    tags = list(scene_object.semantic_tags)
    shape_tag = _shape_tag(scene_object.type)
    if shape_tag not in tags and scene_object.type not in {"image", "plantuml"}:
        tags.append(shape_tag)
    return {
        "type": scene_object.type,
        "name": scene_object.name,
        "layer_id": scene_object.layer_id,
        "group_id": scene_object.group_id,
        "semantic_tags": tags,
        "transform": {},
        "geometry": scene_object.geometry,
        "style": scene_object.style.model_dump(),
        "z_index": scene_object.z_index if scene_object.z_index else index,
    }


def compile_scene_graph_to_command_plan(raw_text: str, normalized_text: str, graph: AgentSceneGraph) -> CommandPlan:
    if graph.requires_confirmation:
        return CommandPlan(
            raw_text=raw_text,
            normalized_text=normalized_text,
            operations=[],
            scene_plan=ScenePlan(
                intent=graph.intent,
                summary=graph.summary,
                steps=[
                    ScenePlanStep(
                        step_id="agent-confirmation",
                        title="确认复杂绘图计划",
                        intent="ask_confirmation",
                        target={"domain": graph.domain, "risk_level": graph.risk_level},
                        operation_indexes=[],
                    )
                ],
                expected_object_count=len(graph.objects) or None,
            ),
            confidence=graph.confidence,
            requires_confirmation=True,
            clarification_question=graph.clarification_question or "这条指令需要确认后再执行, 请补充或确认绘图计划。",
            risk_level=graph.risk_level,
            explanation=graph.summary,
            planner_source="agent",
        )

    operations: list[OperationRequest] = []
    for index, scene_object in enumerate(graph.objects):
        operations.append(
            OperationRequest(
                operation_type="add_object",
                payload={"object": _to_drawing_object(scene_object, index)},
            )
        )
    if not operations:
        raise SceneGraphCompileError("Agent SceneGraph 没有可执行对象")

    return CommandPlan(
        raw_text=raw_text,
        normalized_text=normalized_text,
        operations=operations,
        scene_plan=ScenePlan(
            intent=graph.intent,
            summary=graph.summary,
            steps=[
                ScenePlanStep(
                    step_id="agent-scene-graph",
                    title="生成结构化场景图",
                    intent="scene_graph_to_vector_ops",
                    target={"domain": graph.domain, "relations": [relation.model_dump() for relation in graph.relations]},
                    operation_indexes=list(range(len(operations))),
                )
            ],
            expected_object_count=len(operations),
        ),
        confidence=min(graph.confidence, 0.84),
        requires_confirmation=False,
        risk_level=graph.risk_level,
        explanation=graph.summary,
        planner_source="agent",
    )
