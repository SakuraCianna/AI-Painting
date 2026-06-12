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


class ArtworkCreateRequest(BaseModel):
    title: str = "未命名作品"
    width: int = 1024
    height: int = 768
    background: str = "#ffffff"


class ArtworkUpdateRequest(BaseModel):
    title: str | None = None
    width: int | None = None
    height: int | None = None
    background: str | None = None


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


class CommandPlan(BaseModel):
    raw_text: str
    normalized_text: str
    operations: list[OperationRequest]
    confidence: float = 0.85
    requires_confirmation: bool = False
    clarification_question: str | None = None
    risk_level: str = "low"


class CommandParseRequest(BaseModel):
    text: str


class CommandExecutionResponse(BaseModel):
    message: str
    plan: CommandPlan
    artwork: ArtworkResponse | None = None


class OperationResponse(BaseModel):
    message: str
    artwork: ArtworkResponse
