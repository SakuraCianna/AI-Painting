from __future__ import annotations

import json

from app.asr_evaluation import (
    edit_distance,
    load_asr_evaluation_manifest,
    normalize_transcript,
    score_transcript,
    summarize_asr_evaluation_results,
)


def test_normalize_transcript_removes_punctuation_and_spaces() -> None:
    assert normalize_transcript("  画 一个，蓝色圆形。 ") == "画一个蓝色圆形"


def test_score_transcript_returns_character_error_rate() -> None:
    score = score_transcript("画一个圆", "画一个圈")

    assert score["edit_distance"] == 1
    assert score["character_count"] == 4
    assert score["cer"] == 0.25
    assert score["exact_match"] is False


def test_edit_distance_handles_insertions_and_deletions() -> None:
    assert edit_distance(list("abc"), list("abdc")) == 1
    assert edit_distance(list("abc"), list("ac")) == 1


def test_load_asr_evaluation_manifest_resolves_relative_paths(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "samples": [
                    {
                        "id": "circle-basic",
                        "audio_path": "audio/circle.wav",
                        "expected_text": "画一个圆",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    samples = load_asr_evaluation_manifest(manifest)

    assert samples[0].id == "circle-basic"
    assert samples[0].audio_path == tmp_path / "audio" / "circle.wav"
    assert samples[0].language == "zh"


def test_summarize_asr_evaluation_results_reports_cer_and_latency() -> None:
    summary = summarize_asr_evaluation_results(
        [
            {
                "status": "success",
                "provider": "xiaomi",
                "latency_ms": 100,
                "score": {"cer": 0.0, "exact_match": True},
            },
            {
                "status": "success",
                "provider": "local",
                "latency_ms": 300,
                "score": {"cer": 0.5, "exact_match": False},
            },
            {"status": "failed", "error": "unavailable"},
        ]
    )

    assert summary["sample_count"] == 3
    assert summary["success_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["exact_match_count"] == 1
    assert summary["average_cer"] == 0.25
    assert summary["p75_latency_ms"] == 300
    assert summary["provider_counts"] == {"local": 1, "xiaomi": 1}
