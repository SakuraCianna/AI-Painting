from __future__ import annotations

import json

from app.image_evaluation import load_image_evaluation_manifest, summarize_image_evaluation_results


def test_load_image_evaluation_manifest_defaults_and_validates_samples(tmp_path) -> None:
    manifest = tmp_path / "image-samples.json"
    manifest.write_text(
        json.dumps(
            {
                "samples": [
                    {
                        "id": "ink-landscape",
                        "prompt": "生成一张国风水墨山水画",
                    },
                    {
                        "id": "polish-landscape",
                        "task": "image_edit",
                        "prompt": "让云雾更丰富",
                        "width": 640,
                        "height": 360,
                        "input_image_data_url": "data:image/png;base64,AAAA",
                        "source_prompt": "水墨山水",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    samples = load_image_evaluation_manifest(manifest)

    assert samples[0].id == "ink-landscape"
    assert samples[0].task == "text_to_image"
    assert samples[0].width == 1024
    assert samples[0].height == 768
    assert samples[1].task == "image_edit"
    assert samples[1].width == 640
    assert samples[1].height == 360
    assert samples[1].source_prompt == "水墨山水"


def test_load_image_evaluation_manifest_rejects_unknown_task(tmp_path) -> None:
    manifest = tmp_path / "image-samples.json"
    manifest.write_text(json.dumps({"samples": [{"id": "bad", "task": "video", "prompt": "生成视频"}]}), encoding="utf-8")

    try:
        load_image_evaluation_manifest(manifest)
    except ValueError as exc:
        assert "不支持的图片评测任务" in str(exc)
    else:
        raise AssertionError("manifest should reject unsupported image task")


def test_summarize_image_evaluation_results_reports_readiness_gate() -> None:
    summary = summarize_image_evaluation_results(
        [
            {
                "status": "success",
                "task": "text_to_image",
                "provider": "openai_compatible",
                "width": 1024,
                "height": 768,
                "latency_ms": 12_000,
            },
            {
                "status": "success",
                "task": "image_edit",
                "provider": "openai_compatible",
                "width": 1024,
                "height": 768,
                "latency_ms": 18_000,
            },
            {
                "status": "failed",
                "task": "text_to_image",
                "error": "HTTP 502",
            },
        ]
    )

    assert summary["sample_count"] == 3
    assert summary["success_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["provider_counts"] == {"openai_compatible": 2}
    assert summary["task_counts"] == {"image_edit": 1, "text_to_image": 1}
    assert summary["size_counts"] == {"1024x768": 2}
    assert summary["readiness_gate"]["status"] == "fail"
    assert summary["readiness_gate"]["failure_reasons"] == ["success_rate_below_threshold"]


def test_summarize_image_evaluation_results_passes_when_successful_and_fast_enough() -> None:
    summary = summarize_image_evaluation_results(
        [
            {
                "status": "success",
                "task": "text_to_image",
                "provider": "openai_official",
                "width": 1536,
                "height": 1024,
                "latency_ms": 20_000,
            },
            {
                "status": "success",
                "task": "text_to_image",
                "provider": "openai_official",
                "width": 1536,
                "height": 1024,
                "latency_ms": 22_000,
            },
        ]
    )

    assert summary["success_rate"] == 1.0
    assert summary["readiness_gate"]["status"] == "pass"
    assert summary["readiness_gate"]["failure_reasons"] == []
