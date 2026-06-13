from __future__ import annotations

import json
from pathlib import Path
import asyncio

from app.command_parser import parse_command
from app import main


EVALUATION_PATH = Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "complex_voice_commands.json"
ASR_TRANSCRIPTS_PATH = Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "complex_voice_command_asr_transcripts.json"


def test_complex_voice_command_evaluation_set_is_well_formed() -> None:
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases]
    assert len(cases) == 100
    assert len(ids) == len(set(ids))
    assert {"rules", "agent", "planner_expected"}.issubset({case["tier"] for case in cases})
    assert {case["tier"] for case in cases}.issubset({"rules", "agent", "planner_expected"})


def test_complex_voice_command_asr_transcripts_cover_evaluation_set() -> None:
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    transcript_manifest = json.loads(ASR_TRANSCRIPTS_PATH.read_text(encoding="utf-8"))
    entries = transcript_manifest["transcripts"]
    case_ids = {case["id"] for case in cases}
    transcript_case_ids = {entry["case_id"] for entry in entries}

    assert transcript_manifest["metadata"]["status"] in {"reference_seed", "real_samples"}
    assert case_ids.issubset(transcript_case_ids)
    assert transcript_case_ids.issubset(case_ids)
    assert all(entry["transcript"].strip() for entry in entries)
    assert all(entry["source"] in {"reference", "xiaomi", "local", "web_speech"} for entry in entries)


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
        if case.get("expected_target_position"):
            assert plan.operations[0].payload["target"]["position"] == case["expected_target_position"], case["id"]
        if case.get("expected_target_rank"):
            assert plan.operations[0].payload["target"]["rank"] == case["expected_target_rank"], case["id"]
        if case.get("expected_target_corner"):
            assert plan.operations[0].payload["target"]["corner"] == case["expected_target_corner"], case["id"]
        if case.get("expected_target_region"):
            assert plan.operations[0].payload["target_region"] == case["expected_target_region"], case["id"]
        if case.get("expected_target_subject"):
            assert plan.operations[0].payload["target_subject"] == case["expected_target_subject"], case["id"]
        if case.get("expected_adjustment"):
            assert plan.operations[0].payload["adjustment"] == case["expected_adjustment"], case["id"]


def test_planner_expected_commands_require_clarification_in_rules_layer() -> None:
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    for case in cases:
        if case["tier"] != "planner_expected":
            continue
        plan = parse_command(case["text"])
        assert plan.requires_confirmation is True, case["id"]
        assert plan.operations == [], case["id"]
        assert plan.scene_plan is not None, case["id"]


def test_agent_tier_complex_voice_commands_match_expected_plans(monkeypatch) -> None:
    monkeypatch.setenv("AI_PAINTING_ENABLE_AGENT_PLANNER", "true")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    cases = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    for case in cases:
        if case["tier"] != "agent":
            continue
        plan = asyncio.run(main.build_command_plan(case["text"]))
        assert [operation.operation_type for operation in plan.operations] == case["expected_operation_types"], case["id"]
        expected_object_types = case.get("expected_object_types")
        if expected_object_types:
            objects = [operation.payload["object"] for operation in plan.operations if "object" in operation.payload]
            assert [obj["type"] for obj in objects] == expected_object_types, case["id"]
