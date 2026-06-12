from __future__ import annotations

import asyncio

from app.llm_planner import LlmPlannerError
from app.schemas import CommandPlan, OperationRequest


def test_build_command_plan_uses_mimo_for_unclear_complex_command(monkeypatch) -> None:
    from app import main

    async def fake_plan_with_mimo(text: str) -> CommandPlan:
        return CommandPlan(
            raw_text=text,
            normalized_text=text,
            operations=[
                OperationRequest(
                    operation_type="add_object",
                    payload={
                        "object": {
                            "type": "circle",
                            "name": "太阳",
                            "geometry": {"cx": 512, "cy": 160, "radius": 70},
                            "style": {"fill": "#facc15", "stroke": "#facc15", "strokeWidth": 2, "opacity": 1},
                        }
                    },
                )
            ],
            confidence=0.8,
        )

    monkeypatch.setenv("AI_PAINTING_ENABLE_LLM_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_mimo", fake_plan_with_mimo)

    plan = asyncio.run(main.build_command_plan("画一个森林场景然后加一些层次"))

    assert plan.operations[0].payload["object"]["name"] == "太阳"


def test_build_command_plan_falls_back_when_mimo_fails(monkeypatch) -> None:
    from app import main

    async def fake_plan_with_mimo(_: str) -> CommandPlan:
        raise LlmPlannerError("network failed")

    monkeypatch.setenv("AI_PAINTING_ENABLE_LLM_PLANNER", "true")
    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setattr(main, "plan_with_mimo", fake_plan_with_mimo)

    plan = asyncio.run(main.build_command_plan("画一个森林场景然后加一些层次"))

    assert plan.requires_confirmation is True
    assert plan.operations == []
