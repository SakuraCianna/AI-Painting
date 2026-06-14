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
    title: str = Field("未命名作品", min_length=1, max_length=80)
    width: int = Field(1024, ge=64, le=4096)
    height: int = Field(768, ge=64, le=4096)
    background: str = Field("#ffffff", min_length=1, max_length=64)


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
    text: str = Field(..., min_length=1, max_length=500)
    canvas_image_data_url: str | None = Field(default=None, min_length=1, max_length=16_000_000)


class AsrTranscriptionRequest(BaseModel):
    audio_data_url: str = Field(..., min_length=1, max_length=10_500_000)
    language: str = Field("zh", min_length=1, max_length=20)


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
    text: str = Field(..., min_length=1, max_length=300)
    voice: str | None = Field(default=None, max_length=80)
    style: str | None = Field(default=None, max_length=80)


class TtsSynthesisResponse(BaseModel):
    audio_data_url: str
    provider: str = "xiaomi"
    provider_label: str = "小米 MiMo TTS"
    format: str = "wav"


class CommandExecutionMetrics(BaseModel):
    rule_parse_ms: float | None = None
    llm_planner_ms: float | None = None
    agent_planner_ms: float | None = None
    planner_total_ms: float | None = None
    execute_ms: float | None = None
    total_ms: float | None = None
    llm_attempted: bool = False
    llm_succeeded: bool = False
    agent_attempted: bool = False
    agent_succeeded: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    fallback_error_type: str | None = None
    planner_source: str | None = None


class LatencyMetricStats(BaseModel):
    count: int = 0
    average_ms: float | None = None
    p50_ms: float | None = None
    p75_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None


class LatencyMetricsSummary(BaseModel):
    artwork_id: str | None = None
    limit: int = 200
    sample_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    needs_confirmation_count: int = 0
    canceled_count: int = 0
    planner_sources: dict[str, int] = Field(default_factory=dict)
    fallback_reasons: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, LatencyMetricStats] = Field(default_factory=dict)
    latest_created_at: str | None = None


class CommandExecutionResponse(BaseModel):
    message: str
    plan: CommandPlan
    artwork: ArtworkResponse | None = None
    metrics: CommandExecutionMetrics = Field(default_factory=CommandExecutionMetrics)


class OperationResponse(BaseModel):
    message: str
    artwork: ArtworkResponse
