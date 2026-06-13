from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from .schemas import LatencyMetricStats, LatencyMetricsSummary


TRACKED_LATENCY_KEYS = ("rule_parse_ms", "llm_planner_ms", "agent_planner_ms", "planner_total_ms", "execute_ms", "total_ms")


def _round_ms(value: float) -> float:
    return round(value, 2)


def percentile(values: list[float], percentile_value: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((percentile_value / 100) * len(ordered)) - 1)
    return _round_ms(ordered[index])


def summarize_values(values: list[float]) -> LatencyMetricStats:
    if not values:
        return LatencyMetricStats(count=0)
    return LatencyMetricStats(
        count=len(values),
        average_ms=_round_ms(sum(values) / len(values)),
        p50_ms=percentile(values, 50),
        p75_ms=percentile(values, 75),
        p95_ms=percentile(values, 95),
        max_ms=_round_ms(max(values)),
    )


def _parse_latency(raw_latency: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_latency)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_value(row: Mapping[str, Any], key: str) -> Any:
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def summarize_latency_rows(rows: Iterable[Mapping[str, Any]], *, artwork_id: str | None = None, limit: int = 200) -> LatencyMetricsSummary:
    metric_values: dict[str, list[float]] = {key: [] for key in TRACKED_LATENCY_KEYS}
    statuses: Counter[str] = Counter()
    planner_sources: Counter[str] = Counter()
    latest_created_at: str | None = None
    sample_count = 0

    for row in rows:
        sample_count += 1
        status = str(_row_value(row, "status") or "unknown")
        statuses[status] += 1
        created_at = _row_value(row, "created_at")
        latest_created_at = latest_created_at or (str(created_at) if created_at else None)
        latency = _parse_latency(str(_row_value(row, "latency_json") or "{}"))
        planner_source = latency.get("planner_source")
        if planner_source:
            planner_sources[str(planner_source)] += 1
        for key in TRACKED_LATENCY_KEYS:
            value = latency.get(key)
            if isinstance(value, int | float):
                metric_values[key].append(float(value))

    return LatencyMetricsSummary(
        artwork_id=artwork_id,
        limit=limit,
        sample_count=sample_count,
        success_count=statuses["success"],
        failed_count=statuses["failed"],
        needs_confirmation_count=statuses["needs_confirmation"],
        canceled_count=statuses["canceled"],
        planner_sources=dict(sorted(planner_sources.items())),
        metrics={key: summarize_values(values) for key, values in metric_values.items()},
        latest_created_at=latest_created_at,
    )
