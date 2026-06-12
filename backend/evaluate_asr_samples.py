from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.asr import AsrProvidersUnavailable, get_asr_provider_status, transcribe_audio_data_url
from app.asr_evaluation import (
    AsrEvaluationSample,
    load_asr_evaluation_manifest,
    score_transcript,
    summarize_asr_evaluation_results,
)
from app.config import load_env_file


def audio_file_to_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type == "audio/x-wav":
        mime_type = "audio/wav"
    if mime_type not in {"audio/wav", "audio/mpeg", "audio/mp3"}:
        raise ValueError(f"不支持的音频格式: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def evaluate_sample(sample: AsrEvaluationSample) -> dict[str, Any]:
    try:
        response = await transcribe_audio_data_url(audio_file_to_data_url(sample.audio_path), sample.language)
    except AsrProvidersUnavailable as exc:
        return {
            "id": sample.id,
            "audio_path": str(sample.audio_path),
            "expected_text": sample.expected_text,
            "status": "failed",
            "error": str(exc),
            "attempts": [attempt.model_dump() for attempt in exc.attempts],
        }
    except (OSError, ValueError, RuntimeError) as exc:
        return {
            "id": sample.id,
            "audio_path": str(sample.audio_path),
            "expected_text": sample.expected_text,
            "status": "failed",
            "error": str(exc),
        }

    return {
        "id": sample.id,
        "audio_path": str(sample.audio_path),
        "expected_text": sample.expected_text,
        "actual_text": response.text,
        "language": sample.language,
        "provider": response.provider,
        "provider_label": response.provider_label,
        "latency_ms": response.metrics.total_ms,
        "attempts": [attempt.model_dump() for attempt in response.attempts],
        "score": score_transcript(sample.expected_text, response.text),
        "status": "success",
    }


async def run_evaluation(manifest_path: Path) -> dict[str, Any]:
    samples = load_asr_evaluation_manifest(manifest_path)
    results = [await evaluate_sample(sample) for sample in samples]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_path),
        "provider_status": get_asr_provider_status().model_dump(),
        "summary": summarize_asr_evaluation_results(results),
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate AI Painting ASR providers with a local audio manifest.")
    parser.add_argument("manifest", type=Path, help="ASR sample manifest JSON path")
    parser.add_argument("--output", type=Path, help="Write evaluation JSON to this path")
    parser.add_argument("--providers", help="Override AI_PAINTING_ASR_PROVIDERS for this run, for example xiaomi or local")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file()
    if args.providers:
        os.environ["AI_PAINTING_ASR_PROVIDERS"] = args.providers
    report = asyncio.run(run_evaluation(args.manifest))
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
