from __future__ import annotations

import json
from pathlib import Path

from app.command_parser import parse_command


EVALUATION_PATH = Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "complex_voice_commands.json"


def test_complex_voice_command_evaluation_set_is_well_formed() -> None:
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases]
    assert len(cases) >= 12
    assert len(ids) == len(set(ids))
    assert {case["tier"] for case in cases}.issubset({"rules", "planner_expected"})


def test_rules_tier_complex_voice_commands_match_expected_plans() -> None:
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    for case in cases:
        if case["tier"] != "rules":
            continue
        plan = parse_command(case["text"])
        assert [operation.operation_type for operation in plan.operations] == case["expected_operation_types"], case["id"]
        expected_object_types = case.get("expected_object_types")
        if expected_object_types:
            objects = [operation.payload["object"] for operation in plan.operations if "object" in operation.payload]
            assert [obj["type"] for obj in objects] == expected_object_types, case["id"]
        if case.get("expected_semantic_tag"):
            obj = plan.operations[0].payload["object"]
            assert case["expected_semantic_tag"] in obj["semantic_tags"], case["id"]
        if case.get("expected_layer_id"):
            obj = plan.operations[0].payload["object"]
            assert obj["layer_id"] == case["expected_layer_id"], case["id"]
        if case.get("expected_target_semantic_tag"):
            assert plan.operations[0].payload["target"]["semantic_tag"] == case["expected_target_semantic_tag"], case["id"]
        if case.get("expected_target_layer_id"):
            assert plan.operations[0].payload["target"]["layer_id"] == case["expected_target_layer_id"], case["id"]


def test_planner_expected_commands_require_clarification_in_rules_layer() -> None:
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    for case in cases:
        if case["tier"] != "planner_expected":
            continue
        plan = parse_command(case["text"])
        assert plan.requires_confirmation is True, case["id"]
        assert plan.operations == [], case["id"]
        assert plan.scene_plan is not None, case["id"]
