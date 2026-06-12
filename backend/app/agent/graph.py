from __future__ import annotations

from typing import TypedDict

from ..schemas import CommandPlan
from .compiler import compile_scene_graph_to_command_plan
from .scene_graph import AgentSceneGraph
from .validator import repair_scene_graph, validate_scene_graph_for_compilation


class AgentGraphState(TypedDict, total=False):
    text: str
    normalized_text: str
    scene_graph: AgentSceneGraph
    repaired_scene_graph: AgentSceneGraph
    plan: CommandPlan


def _repair_node(state: AgentGraphState) -> AgentGraphState:
    return {"repaired_scene_graph": repair_scene_graph(state["scene_graph"])}


def _validate_node(state: AgentGraphState) -> AgentGraphState:
    return {"repaired_scene_graph": validate_scene_graph_for_compilation(state["repaired_scene_graph"])}


def _compile_node(state: AgentGraphState) -> AgentGraphState:
    return {
        "plan": compile_scene_graph_to_command_plan(
            state["text"],
            state["normalized_text"],
            state["repaired_scene_graph"],
        )
    }


def _run_sync_graph(text: str, normalized_text: str, scene_graph: AgentSceneGraph) -> CommandPlan:
    state: AgentGraphState = {"text": text, "normalized_text": normalized_text, "scene_graph": scene_graph}
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
        builder.add_node("repair_scene_graph", _repair_node)
        builder.add_node("validate_scene_graph", _validate_node)
        builder.add_node("compile_plan", _compile_node)
        builder.add_edge(START, "repair_scene_graph")
        builder.add_edge("repair_scene_graph", "validate_scene_graph")
        builder.add_edge("validate_scene_graph", "compile_plan")
        builder.add_edge("compile_plan", END)
        runtime = builder.compile()
        result = runtime.invoke({"text": text, "normalized_text": normalized_text, "scene_graph": scene_graph})
        return result["plan"]
    except Exception:
        return _run_sync_graph(text, normalized_text, scene_graph)
