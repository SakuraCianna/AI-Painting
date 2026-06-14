from __future__ import annotations

import base64
import struct
from dataclasses import dataclass, field
from time import perf_counter

from .asr import normalize_asr_language


class StreamingAsrProtocolError(ValueError):
    def __init__(self, message: str, *, code: str = "protocol_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class StreamingAsrSession:
    language: str = "zh"
    sample_rate: int = 16000
    max_audio_bytes: int = 7_500_000
    chunks: list[bytes] = field(default_factory=list)
    received_bytes: int = 0
    started_at: float = field(default_factory=perf_counter)

    def configure(self, *, language: str | None = None, sample_rate: int | None = None, max_audio_bytes: int | None = None) -> None:
        if language is not None:
            self.language = normalize_asr_language(language)
        if sample_rate is not None:
            if sample_rate < 8000 or sample_rate > 48000:
                raise StreamingAsrProtocolError("ASR 流式采样率必须在 8000 到 48000 之间", code="invalid_sample_rate")
            self.sample_rate = sample_rate
        if max_audio_bytes is not None:
            self.max_audio_bytes = max_audio_bytes

    def append_pcm16(self, audio_bytes: bytes) -> None:
        if len(audio_bytes) == 0:
            return
        if len(audio_bytes) % 2 != 0:
            raise StreamingAsrProtocolError("ASR 流式音频必须是单声道 PCM16 小端字节", code="invalid_pcm16")
        next_size = self.received_bytes + len(audio_bytes)
        if next_size > self.max_audio_bytes:
            raise StreamingAsrProtocolError("ASR 流式音频过大, 请缩短单次语音指令", code="audio_too_large")
        self.chunks.append(bytes(audio_bytes))
        self.received_bytes = next_size

    def clear(self) -> None:
        self.chunks.clear()
        self.received_bytes = 0
        self.started_at = perf_counter()

    def to_wav_data_url(self) -> str:
        if self.received_bytes <= 0:
            raise StreamingAsrProtocolError("ASR 流式音频为空", code="empty_audio")
        pcm = b"".join(self.chunks)
        wav = _build_mono_pcm16_wav(pcm, self.sample_rate)
        return f"data:audio/wav;base64,{base64.b64encode(wav).decode('ascii')}"


def _build_mono_pcm16_wav(pcm: bytes, sample_rate: int) -> bytes:
    bits_per_sample = 16
    channels = 1
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm)
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", 36 + data_size),
            b"WAVE",
            b"fmt ",
            struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample),
            b"data",
            struct.pack("<I", data_size),
            pcm,
        )
    )
