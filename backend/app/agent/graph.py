from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypedDict

from ..schemas import CommandPlan
from .compiler import compile_scene_graph_to_command_plan
from .model_client import AgentModelError
from .scene_graph import AgentSceneGraph
from .validator import SceneGraphValidationError, repair_scene_graph, validate_scene_graph_for_compilation


SceneGraphBuilder = Callable[[str], Awaitable[AgentSceneGraph]]
SceneGraphRepairer = Callable[[str, AgentSceneGraph, str], Awaitable[AgentSceneGraph]]


class AgentGraphState(TypedDict, total=False):
    text: str
    normalized_text: str
    domain: str
    scene_graph_builder: SceneGraphBuilder
    scene_graph_repairer: SceneGraphRepairer
    scene_graph: AgentSceneGraph
    repaired_scene_graph: AgentSceneGraph
    validation_error: str | None
    repair_attempts: int
    plan: CommandPlan


def _classify_node(state: AgentGraphState) -> AgentGraphState:
    scene_graph = state.get("scene_graph")
    if scene_graph is not None:
        return {"domain": scene_graph.domain}
    text = state["normalized_text"]
    if any(keyword in text for keyword in ("流程图", "结构图", "架构图")):
        return {"domain": "diagram_scene"}
    if any(keyword in text for keyword in ("海报", "封面", "信息图")):
        return {"domain": "layout_scene"}
    if any(keyword in text for keyword in ("客厅", "卧室", "厨房", "办公室", "教室")):
        return {"domain": "interior_vector_scene"}
    return {"domain": "vector_canvas"}


async def _build_scene_graph_node(state: AgentGraphState) -> AgentGraphState:
    if "scene_graph" in state:
        return {"scene_graph": state["scene_graph"]}
    builder = state.get("scene_graph_builder")
    if builder is None:
        raise SceneGraphValidationError("Drawing Agent 缺少 SceneGraph 构建器")
    return {"scene_graph": await builder(state["text"])}


def _repair_node(state: AgentGraphState) -> AgentGraphState:
    return {"repaired_scene_graph": repair_scene_graph(state["scene_graph"])}


def _validate_node(state: AgentGraphState) -> AgentGraphState:
    try:
        return {
            "repaired_scene_graph": validate_scene_graph_for_compilation(state["repaired_scene_graph"]),
            "validation_error": None,
        }
    except SceneGraphValidationError as exc:
        return {"validation_error": str(exc)}


async def _model_repair_node(state: AgentGraphState) -> AgentGraphState:
    repairer = state.get("scene_graph_repairer")
    if repairer is None:
        return {}
    validation_error = state.get("validation_error") or "SceneGraph 校验失败"
    repaired = await repairer(state["text"], state["repaired_scene_graph"], validation_error)
    return {
        "scene_graph": repaired,
        "repair_attempts": state.get("repair_attempts", 0) + 1,
        "validation_error": None,
    }


def _compile_node(state: AgentGraphState) -> AgentGraphState:
    if state.get("validation_error"):
        raise SceneGraphValidationError(state["validation_error"] or "SceneGraph 校验失败")
    return {
        "plan": compile_scene_graph_to_command_plan(
            state["text"],
            state["normalized_text"],
            state["repaired_scene_graph"],
        )
    }


def _route_after_validate(state: AgentGraphState) -> str:
    if state.get("validation_error") and state.get("scene_graph_repairer") and state.get("repair_attempts", 0) < 1:
        return "repair_with_model"
    return "compile_plan"


def _run_sync_graph(text: str, normalized_text: str, scene_graph: AgentSceneGraph) -> CommandPlan:
    state: AgentGraphState = {"text": text, "normalized_text": normalized_text, "scene_graph": scene_graph}
    state.update(_classify_node(state))
    state.update(_repair_node(state))
    state.update(_validate_node(state))
    state.update(_compile_node(state))
    return state["plan"]


def run_agent_graph(text: str, normalized_text: str, scene_graph: AgentSceneGraph) -> CommandPlan:
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return _run_sync_graph(text, normalized_text, scene_graph)

    try:
        builder = StateGraph(AgentGraphState)
        builder.add_node("classify_intent", _classify_node)
        builder.add_node("repair_scene_graph", _repair_node)
        builder.add_node("validate_scene_graph", _validate_node)
        builder.add_node("compile_plan", _compile_node)
        builder.add_edge(START, "classify_intent")
        builder.add_edge("classify_intent", "repair_scene_graph")
        builder.add_edge("repair_scene_graph", "validate_scene_graph")
        builder.add_edge("validate_scene_graph", "compile_plan")
        builder.add_edge("compile_plan", END)
        runtime = builder.compile()
        result = runtime.invoke({"text": text, "normalized_text": normalized_text, "scene_graph": scene_graph})
        return result["plan"]
    except Exception:
        return _run_sync_graph(text, normalized_text, scene_graph)


async def _run_async_sync_graph(
    text: str,
    normalized_text: str,
    *,
    scene_graph: AgentSceneGraph | None,
    scene_graph_builder: SceneGraphBuilder | None,
    scene_graph_repairer: SceneGraphRepairer | None,
) -> CommandPlan:
    state: AgentGraphState = {
        "text": text,
        "normalized_text": normalized_text,
        "repair_attempts": 0,
    }
    if scene_graph is not None:
        state["scene_graph"] = scene_graph
    if scene_graph_builder is not None:
        state["scene_graph_builder"] = scene_graph_builder
    if scene_graph_repairer is not None:
        state["scene_graph_repairer"] = scene_graph_repairer
    state.update(_classify_node(state))
    state.update(await _build_scene_graph_node(state))
    state.update(_repair_node(state))
    state.update(_validate_node(state))
    if state.get("validation_error") and scene_graph_repairer is not None:
        state.update(await _model_repair_node(state))
        state.update(_repair_node(state))
        state.update(_validate_node(state))
    state.update(_compile_node(state))
    return state["plan"]


async def run_drawing_agent_graph(
    text: str,
    normalized_text: str,
    *,
    scene_graph: AgentSceneGraph | None = None,
    scene_graph_builder: SceneGraphBuilder | None = None,
    scene_graph_repairer: SceneGraphRepairer | None = None,
) -> CommandPlan:
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return await _run_async_sync_graph(
            text,
            normalized_text,
            scene_graph=scene_graph,
            scene_graph_builder=scene_graph_builder,
            scene_graph_repairer=scene_graph_repairer,
        )

    try:
        builder = StateGraph(AgentGraphState)
        builder.add_node("classify_intent", _classify_node)
        builder.add_node("build_scene_graph", _build_scene_graph_node)
        builder.add_node("repair_scene_graph", _repair_node)
        builder.add_node("validate_scene_graph", _validate_node)
        builder.add_node("repair_with_model", _model_repair_node)
        builder.add_node("compile_plan", _compile_node)
        builder.add_edge(START, "classify_intent")
        builder.add_edge("classify_intent", "build_scene_graph")
        builder.add_edge("build_scene_graph", "repair_scene_graph")
        builder.add_edge("repair_scene_graph", "validate_scene_graph")
        builder.add_conditional_edges(
            "validate_scene_graph",
            _route_after_validate,
            {
                "repair_with_model": "repair_with_model",
                "compile_plan": "compile_plan",
            },
        )
        builder.add_edge("repair_with_model", "repair_scene_graph")
        builder.add_edge("compile_plan", END)
        runtime = builder.compile()
        initial_state: AgentGraphState = {
            "text": text,
            "normalized_text": normalized_text,
            "repair_attempts": 0,
        }
        if scene_graph is not None:
            initial_state["scene_graph"] = scene_graph
        if scene_graph_builder is not None:
            initial_state["scene_graph_builder"] = scene_graph_builder
        if scene_graph_repairer is not None:
            initial_state["scene_graph_repairer"] = scene_graph_repairer
        result = await runtime.ainvoke(initial_state)
        return result["plan"]
    except AgentModelError:
        raise
    except Exception:
        return await _run_async_sync_graph(
            text,
            normalized_text,
            scene_graph=scene_graph,
            scene_graph_builder=scene_graph_builder,
            scene_graph_repairer=scene_graph_repairer,
        )
