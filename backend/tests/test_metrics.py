from __future__ import annotations

import json

from app.metrics import percentile, summarize_latency_rows


def test_percentile_uses_nearest_rank_for_small_samples() -> None:
    values = [400, 100, 300, 200]

    assert percentile(values, 50) == 200
    assert percentile(values, 75) == 300
    assert percentile(values, 95) == 400


def test_summarize_latency_rows_counts_statuses_and_planner_sources() -> None:
    rows = [
        {
            "status": "success",
            "created_at": "2026-06-12T12:00:00Z",
            "latency_json": json.dumps({"planner_total_ms": 100, "execute_ms": 10, "total_ms": 120, "planner_source": "rules"}),
        },
        {
            "status": "failed",
            "created_at": "2026-06-12T12:00:01Z",
            "latency_json": json.dumps({"planner_total_ms": 300, "execute_ms": 20, "total_ms": 340, "planner_source": "mimo"}),
        },
    ]

    summary = summarize_latency_rows(rows, artwork_id="artwork-1", limit=50)

    assert summary.artwork_id == "artwork-1"
    assert summary.limit == 50
    assert summary.sample_count == 2
    assert summary.success_count == 1
    assert summary.failed_count == 1
    assert summary.planner_sources == {"mimo": 1, "rules": 1}
    assert summary.metrics["planner_total_ms"].p75_ms == 300
    assert summary.metrics["total_ms"].max_ms == 340
