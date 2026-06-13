from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .metrics import percentile


PUNCTUATION_PATTERN = re.compile(r"[\s,.;:!?，。；：！？、'\"“”‘’（）()【】\[\]{}<>《》\-—_]+")
MIN_ASR_SUCCESS_RATE = 0.95
MAX_AVERAGE_CER = 0.05
MAX_P75_LATENCY_MS = 1500


@dataclass(frozen=True)
class AsrEvaluationSample:
    id: str
    audio_path: Path
    expected_text: str
    language: str = "zh"
    notes: str = ""


def normalize_transcript(text: str) -> str:
    return PUNCTUATION_PATTERN.sub("", text.strip().lower())


def edit_distance(expected: Sequence[str], actual: Sequence[str]) -> int:
    previous = list(range(len(actual) + 1))
    for expected_index, expected_item in enumerate(expected, start=1):
        current = [expected_index]
        for actual_index, actual_item in enumerate(actual, start=1):
            substitution_cost = 0 if expected_item == actual_item else 1
            current.append(
                min(
                    previous[actual_index] + 1,
                    current[actual_index - 1] + 1,
                    previous[actual_index - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]


def score_transcript(expected_text: str, actual_text: str) -> dict[str, Any]:
    normalized_expected = normalize_transcript(expected_text)
    normalized_actual = normalize_transcript(actual_text)
    expected_chars = list(normalized_expected)
    actual_chars = list(normalized_actual)
    distance = edit_distance(expected_chars, actual_chars)
    character_count = len(expected_chars)
    if character_count == 0:
        cer = 0.0 if not actual_chars else 1.0
    else:
        cer = distance / character_count
    return {
        "normalized_expected": normalized_expected,
        "normalized_actual": normalized_actual,
        "edit_distance": distance,
        "character_count": character_count,
        "cer": round(cer, 4),
        "exact_match": normalized_expected == normalized_actual,
    }


def _sample_from_payload(payload: dict[str, Any], manifest_dir: Path) -> AsrEvaluationSample:
    audio_path = Path(str(payload["audio_path"]))
    if not audio_path.is_absolute():
        audio_path = manifest_dir / audio_path
    return AsrEvaluationSample(
        id=str(payload["id"]),
        audio_path=audio_path,
        expected_text=str(payload["expected_text"]),
        language=str(payload.get("language") or "zh"),
        notes=str(payload.get("notes") or ""),
    )


def load_asr_evaluation_manifest(path: str | Path) -> list[AsrEvaluationSample]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_samples = payload.get("samples") if isinstance(payload, dict) else payload
    if not isinstance(raw_samples, list):
        raise ValueError("ASR 评测清单必须是数组或包含 samples 数组")
    return [_sample_from_payload(sample, manifest_path.parent) for sample in raw_samples]


def summarize_asr_evaluation_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    result_list = list(results)
    success_results = [result for result in result_list if result.get("status") == "success"]
    cer_values = [float(result["score"]["cer"]) for result in success_results if result.get("score")]
    latency_values = [float(result["latency_ms"]) for result in success_results if isinstance(result.get("latency_ms"), int | float)]
    provider_counts: dict[str, int] = {}
    for result in success_results:
        provider = str(result.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1

    def _average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    success_rate = round(len(success_results) / len(result_list), 4) if result_list else 0.0
    average_cer = _average(cer_values)
    p75_latency_ms = percentile(latency_values, 75) if latency_values else None
    readiness_passed = (
        success_rate >= MIN_ASR_SUCCESS_RATE
        and average_cer is not None
        and average_cer <= MAX_AVERAGE_CER
        and p75_latency_ms is not None
        and p75_latency_ms <= MAX_P75_LATENCY_MS
    )
    failure_reasons = []
    if success_rate < MIN_ASR_SUCCESS_RATE:
        failure_reasons.append("success_rate_below_threshold")
    if average_cer is None or average_cer > MAX_AVERAGE_CER:
        failure_reasons.append("average_cer_above_threshold")
    if p75_latency_ms is None or p75_latency_ms > MAX_P75_LATENCY_MS:
        failure_reasons.append("p75_latency_above_threshold")

    return {
        "sample_count": len(result_list),
        "success_count": len(success_results),
        "failed_count": len(result_list) - len(success_results),
        "exact_match_count": sum(1 for result in success_results if result.get("score", {}).get("exact_match")),
        "average_cer": average_cer,
        "p75_cer": percentile(cer_values, 75) if cer_values else None,
        "p95_cer": percentile(cer_values, 95) if cer_values else None,
        "average_latency_ms": _average(latency_values),
        "p75_latency_ms": p75_latency_ms,
        "p95_latency_ms": percentile(latency_values, 95) if latency_values else None,
        "provider_counts": dict(sorted(provider_counts.items())),
        "readiness_gate": {
            "status": "pass" if readiness_passed else "fail",
            "min_success_rate": MIN_ASR_SUCCESS_RATE,
            "max_average_cer": MAX_AVERAGE_CER,
            "max_p75_latency_ms": MAX_P75_LATENCY_MS,
            "success_rate": success_rate,
            "average_cer": average_cer,
            "p75_latency_ms": p75_latency_ms,
            "failure_reasons": failure_reasons,
        },
    }
