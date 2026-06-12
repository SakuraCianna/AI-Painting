from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DrawingObject(BaseModel):
    id: str
    type: str
    name: str | None = None
    geometry: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    z_index: int = 0
    layer_id: str = "base"
    group_id: str | None = None
    semantic_tags: list[str] = Field(default_factory=list)
    transform: dict[str, Any] = Field(default_factory=dict)


class ArtworkCreateRequest(BaseModel):
    title: str = "未命名作品"
    width: int = 1024
    height: int = 768
    background: str = "#ffffff"


class ArtworkResponse(BaseModel):
    id: str
    title: str
    width: int
    height: int
    background: str
    objects: list[DrawingObject] = Field(default_factory=list)
    created_at: str
    updated_at: str


class OperationRequest(BaseModel):
    operation_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenePlanStep(BaseModel):
    step_id: str
    title: str
    intent: str
    target: dict[str, Any] = Field(default_factory=dict)
    operation_indexes: list[int] = Field(default_factory=list)


class ScenePlan(BaseModel):
    intent: str = "edit_scene"
    summary: str = ""
    steps: list[ScenePlanStep] = Field(default_factory=list)
    expected_object_count: int | None = None


class CommandPlan(BaseModel):
    raw_text: str
    normalized_text: str
    operations: list[OperationRequest]
    scene_plan: ScenePlan | None = None
    confidence: float = 0.85
    requires_confirmation: bool = False
    clarification_question: str | None = None
    risk_level: str = "low"
    explanation: str | None = None
    planner_source: str = "rules"


class CommandParseRequest(BaseModel):
    text: str


class AsrTranscriptionRequest(BaseModel):
    audio_data_url: str
    language: str = "zh"


class AsrProviderAttempt(BaseModel):
    provider: str
    status: str
    message: str
    latency_ms: float | None = None


class AsrTranscriptionMetrics(BaseModel):
    total_ms: float | None = None
    audio_bytes: int | None = None
    attempt_count: int = 0
    successful_provider: str | None = None
    fallback_count: int = 0


class AsrProvidersResponse(BaseModel):
    providers: list[str] = Field(default_factory=list)
    provider_labels: dict[str, str] = Field(default_factory=dict)
    primary_provider: str | None = None
    fallback_provider: str = "web_speech"


class AsrTranscriptionResponse(BaseModel):
    text: str
    provider: str
    provider_label: str
    attempts: list[AsrProviderAttempt] = Field(default_factory=list)
    metrics: AsrTranscriptionMetrics = Field(default_factory=AsrTranscriptionMetrics)


class TtsSynthesisRequest(BaseModel):
    text: str
    voice: str | None = None
    style: str | None = None


class TtsSynthesisResponse(BaseModel):
    audio_data_url: str
    provider: str = "xiaomi"
    provider_label: str = "小米 MiMo TTS"
    format: str = "wav"


class CommandExecutionMetrics(BaseModel):
    rule_parse_ms: float | None = None
    llm_planner_ms: float | None = None
    planner_total_ms: float | None = None
    execute_ms: float | None = None
    total_ms: float | None = None
    llm_attempted: bool = False
    llm_succeeded: bool = False
    fallback_used: bool = False
    planner_source: str | None = None


class CommandExecutionResponse(BaseModel):
    message: str
    plan: CommandPlan
    artwork: ArtworkResponse | None = None
    metrics: CommandExecutionMetrics = Field(default_factory=CommandExecutionMetrics)


class OperationResponse(BaseModel):
    message: str
    artwork: ArtworkResponse
