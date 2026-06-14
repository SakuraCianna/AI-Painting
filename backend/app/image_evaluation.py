from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MIN_IMAGE_SUCCESS_RATE = 0.9
MAX_IMAGE_P75_LATENCY_MS = 30_000


@dataclass(frozen=True)
class ImageEvaluationSample:
    id: str
    task: str
    prompt: str
    width: int
    height: int
    input_image_data_url: str | None = None
    source_prompt: str | None = None
    notes: str | None = None


def _read_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(128, min(parsed, 2048))


def _read_optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_image_evaluation_manifest(path: Path) -> list[ImageEvaluationSample]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ValueError("图片评测清单必须包含 samples 数组")
    loaded: list[ImageEvaluationSample] = []
    for raw_sample in samples:
        if not isinstance(raw_sample, dict):
            raise ValueError("图片评测样本必须是对象")
        task = str(raw_sample.get("task") or "text_to_image").strip()
        if task not in {"text_to_image", "image_edit"}:
            raise ValueError(f"不支持的图片评测任务: {task}")
        sample_id = str(raw_sample.get("id") or "").strip()
        prompt = str(raw_sample.get("prompt") or "").strip()
        if not sample_id or not prompt:
            raise ValueError("图片评测样本必须包含 id 和 prompt")
        loaded.append(
            ImageEvaluationSample(
                id=sample_id,
                task=task,
                prompt=prompt,
                width=_read_int(raw_sample.get("width"), 1024),
                height=_read_int(raw_sample.get("height"), 768),
                input_image_data_url=_read_optional_str(raw_sample.get("input_image_data_url")),
                source_prompt=_read_optional_str(raw_sample.get("source_prompt")),
                notes=_read_optional_str(raw_sample.get("notes")),
            )
        )
    return loaded


def _percentile(values: list[float], percentile_value: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile_value / 100) * (len(ordered) - 1))))
    return round(ordered[index], 2)


def _readiness_gate(success_rate: float, p75_latency_ms: float | None) -> dict[str, Any]:
    failure_reasons: list[str] = []
    if success_rate < MIN_IMAGE_SUCCESS_RATE:
        failure_reasons.append("success_rate_below_threshold")
    if p75_latency_ms is None:
        failure_reasons.append("p75_latency_missing")
    elif p75_latency_ms > MAX_IMAGE_P75_LATENCY_MS:
        failure_reasons.append("p75_latency_above_threshold")
    return {
        "status": "pass" if not failure_reasons else "fail",
        "min_success_rate": MIN_IMAGE_SUCCESS_RATE,
        "max_p75_latency_ms": MAX_IMAGE_P75_LATENCY_MS,
        "success_rate": round(success_rate, 4),
        "p75_latency_ms": p75_latency_ms,
        "failure_reasons": failure_reasons,
    }


def summarize_image_evaluation_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    sample_count = len(results)
    successes = [result for result in results if result.get("status") == "success"]
    failed_count = sample_count - len(successes)
    latencies = [float(result["latency_ms"]) for result in successes if isinstance(result.get("latency_ms"), int | float)]
    provider_counts: dict[str, int] = {}
    task_counts: dict[str, int] = {}
    size_counts: dict[str, int] = {}
    for result in successes:
        provider = str(result.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        task = str(result.get("task") or "unknown")
        task_counts[task] = task_counts.get(task, 0) + 1
        width = result.get("width")
        height = result.get("height")
        if isinstance(width, int) and isinstance(height, int):
            size_key = f"{width}x{height}"
            size_counts[size_key] = size_counts.get(size_key, 0) + 1
    success_rate = len(successes) / sample_count if sample_count else 0.0
    p75_latency_ms = _percentile(latencies, 75)
    return {
        "sample_count": sample_count,
        "success_count": len(successes),
        "failed_count": failed_count,
        "success_rate": round(success_rate, 4),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "p50_latency_ms": _percentile(latencies, 50),
        "p75_latency_ms": p75_latency_ms,
        "p95_latency_ms": _percentile(latencies, 95),
        "provider_counts": dict(sorted(provider_counts.items())),
        "task_counts": dict(sorted(task_counts.items())),
        "size_counts": dict(sorted(size_counts.items())),
        "readiness_gate": _readiness_gate(success_rate, p75_latency_ms),
    }
