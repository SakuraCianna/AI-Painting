from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile


DEFAULT_MODEL_ID = "Qwen/Qwen3-ASR-0.6B"
LANGUAGE_MAP = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh_cn": "Chinese",
    "cmn": "Chinese",
    "yue": "Cantonese",
    "cantonese": "Cantonese",
    "en": "English",
    "auto": None,
}


@dataclass
class Qwen3AsrSettings:
    model_id: str = DEFAULT_MODEL_ID
    device: str = "auto"
    dtype: str = "auto"
    max_new_tokens: int = 256
    max_batch_size: int = 1
    max_audio_bytes: int = 7_500_000
    mock_text: str | None = None


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_settings() -> Qwen3AsrSettings:
    return Qwen3AsrSettings(
        model_id=os.getenv("QWEN3_ASR_MODEL", DEFAULT_MODEL_ID),
        device=os.getenv("QWEN3_ASR_DEVICE", "auto"),
        dtype=os.getenv("QWEN3_ASR_DTYPE", "auto"),
        max_new_tokens=_read_int_env("QWEN3_ASR_MAX_NEW_TOKENS", 256),
        max_batch_size=_read_int_env("QWEN3_ASR_MAX_BATCH_SIZE", 1),
        max_audio_bytes=_read_int_env("QWEN3_ASR_MAX_AUDIO_BYTES", 7_500_000),
        mock_text=os.getenv("QWEN3_ASR_MOCK_TEXT"),
    )


def normalize_language(language: str) -> str | None:
    normalized = language.strip().lower()
    return LANGUAGE_MAP.get(normalized, language.strip() or None)


def _extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        for key in ("text", "transcript", "content"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise RuntimeError("Qwen3-ASR 没有返回可用文本")


class Qwen3AsrRuntime:
    def __init__(self) -> None:
        self.settings = load_settings()
        self._model: Any | None = None

    @property
    def model_id(self) -> str:
        return self.settings.model_id

    def _torch_dtype(self, torch_module: Any) -> Any:
        if self.settings.dtype == "float16":
            return torch_module.float16
        if self.settings.dtype == "float32":
            return torch_module.float32
        if self.settings.dtype == "bfloat16":
            return torch_module.bfloat16
        return torch_module.bfloat16 if torch_module.cuda.is_available() else torch_module.float32

    def _device(self, torch_module: Any) -> str:
        if self.settings.device != "auto":
            return self.settings.device
        return "cuda:0" if torch_module.cuda.is_available() else "cpu"

    def load_model(self) -> Any:
        self.settings = load_settings()
        if self.settings.mock_text:
            return None
        if self._model is not None:
            return self._model
        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise RuntimeError(
                "未安装 Qwen3-ASR 本地依赖, 请执行 pip install -r backend\\requirements-local-asr.txt"
            ) from exc

        self._model = Qwen3ASRModel.from_pretrained(
            self.settings.model_id,
            device_map=self._device(torch),
            dtype=self._torch_dtype(torch),
            max_new_tokens=self.settings.max_new_tokens,
            max_inference_batch_size=self.settings.max_batch_size,
        )
        return self._model

    def transcribe(self, audio_path: Path, language: str) -> str:
        self.settings = load_settings()
        if self.settings.mock_text:
            return self.settings.mock_text
        model = self.load_model()
        results = model.transcribe(audio=str(audio_path), language=normalize_language(language))
        if isinstance(results, list) and results:
            return _extract_text(results[0])
        return _extract_text(results)


runtime = Qwen3AsrRuntime()
app = FastAPI(title="AI Painting Qwen3-ASR Local Service")


@app.get("/health")
def health() -> dict[str, str]:
    settings = load_settings()
    return {
        "status": "ok",
        "provider": "qwen3-asr",
        "model": settings.model_id,
        "device": settings.device,
    }


@app.post("/asr")
async def transcribe(file: UploadFile = File(...), language: str = Form("zh")) -> dict[str, Any]:
    settings = load_settings()
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频文件为空")
    if len(audio_bytes) > settings.max_audio_bytes:
        raise HTTPException(status_code=400, detail="音频文件过大, 请缩短单次语音指令")

    suffix = Path(file.filename or "voice-command.wav").suffix or ".wav"
    started_at = perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="ai-painting-qwen3-asr-") as tmp_dir:
            audio_path = Path(tmp_dir) / f"voice-command{suffix}"
            audio_path.write_bytes(audio_bytes)
            text = runtime.transcribe(audio_path, language)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "text": text,
        "transcript": text,
        "provider": "qwen3-asr",
        "model": settings.model_id,
        "language": normalize_language(language),
        "latency_ms": round((perf_counter() - started_at) * 1000, 2),
    }
