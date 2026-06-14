from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from app.config import load_env_file
from app.image_evaluation import ImageEvaluationSample, load_image_evaluation_manifest, summarize_image_evaluation_results
from app.image_generation import ImageGenerationError, generate_image_object, polish_image_object


async def evaluate_sample(sample: ImageEvaluationSample) -> dict[str, Any]:
    started_at = perf_counter()
    try:
        if sample.task == "image_edit":
            if not sample.input_image_data_url:
                raise ImageGenerationError("图生图评测样本缺少 input_image_data_url")
            image_object = await polish_image_object(
                {
                    "prompt": sample.prompt,
                    "input_image_data_url": sample.input_image_data_url,
                    "source_prompt": sample.source_prompt,
                    "width": sample.width,
                    "height": sample.height,
                },
                fallback_width=sample.width,
                fallback_height=sample.height,
            )
        else:
            image_object = await generate_image_object({"prompt": sample.prompt, "width": sample.width, "height": sample.height})
    except (ImageGenerationError, OSError, RuntimeError, ValueError) as exc:
        return {
            "id": sample.id,
            "task": sample.task,
            "prompt": sample.prompt,
            "width": sample.width,
            "height": sample.height,
            "status": "failed",
            "error": str(exc),
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }

    geometry = image_object["geometry"]
    src = str(geometry.get("src") or "")
    return {
        "id": sample.id,
        "task": sample.task,
        "prompt": sample.prompt,
        "width": int(geometry.get("width") or sample.width),
        "height": int(geometry.get("height") or sample.height),
        "provider": str(geometry.get("provider") or "unknown"),
        "source_kind": "data_url" if src.startswith("data:image/") else "url" if src else "missing",
        "source_bytes": len(src.encode("utf-8")),
        "status": "success",
        "latency_ms": round((perf_counter() - started_at) * 1000, 2),
    }


async def run_evaluation(manifest_path: Path) -> dict[str, Any]:
    samples = load_image_evaluation_manifest(manifest_path)
    results = [await evaluate_sample(sample) for sample in samples]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_path),
        "provider_config": {
            "text_image_provider": os.getenv("AI_PAINTING_IMAGE_PROVIDER", "placeholder"),
            "text_image_model": os.getenv("AI_PAINTING_TEXT_IMAGE_MODEL"),
            "image_edit_provider": os.getenv("AI_PAINTING_IMAGE_EDIT_PROVIDER", "placeholder"),
            "image_edit_model": os.getenv("AI_PAINTING_IMAGE_EDIT_MODEL"),
            "openai_fallback_configured": bool(os.getenv("AI_PAINTING_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")),
        },
        "summary": summarize_image_evaluation_results(results),
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate AI Painting image generation and image edit providers.")
    parser.add_argument("manifest", type=Path, help="Image provider sample manifest JSON path")
    parser.add_argument("--output", type=Path, help="Write evaluation JSON to this path")
    parser.add_argument("--text-provider", help="Override AI_PAINTING_IMAGE_PROVIDER for this run")
    parser.add_argument("--edit-provider", help="Override AI_PAINTING_IMAGE_EDIT_PROVIDER for this run")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file()
    if args.text_provider:
        os.environ["AI_PAINTING_IMAGE_PROVIDER"] = args.text_provider
    if args.edit_provider:
        os.environ["AI_PAINTING_IMAGE_EDIT_PROVIDER"] = args.edit_provider
    report = asyncio.run(run_evaluation(args.manifest))
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
