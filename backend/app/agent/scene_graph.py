from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AgentObjectType = Literal[
    "rect",
    "circle",
    "ellipse",
    "triangle",
    "line",
    "arrow",
    "star",
    "text",
    "polygon",
    "path",
    "bezier",
    "image",
    "plantuml",
]


class AgentStyle(BaseModel):
    fill: str = "#2563eb"
    stroke: str = "#111827"
    strokeWidth: float = Field(2, ge=0, le=40)
    opacity: float = Field(1, ge=0, le=1)


class AgentSceneObject(BaseModel):
    object_id: str = Field(..., min_length=1, max_length=64)
    type: AgentObjectType
    name: str = Field(..., min_length=1, max_length=80)
    layer_id: str = Field("middle", min_length=1, max_length=40)
    group_id: str | None = Field(default=None, max_length=80)
    semantic_tags: list[str] = Field(default_factory=list, max_length=16)
    geometry: dict[str, Any] = Field(default_factory=dict)
    style: AgentStyle = Field(default_factory=AgentStyle)
    z_index: int = Field(0, ge=-1000, le=1000)
    role: str | None = Field(default=None, max_length=80)

    @field_validator("semantic_tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = []
        for tag in value:
            clean = tag.strip()
            if clean and clean not in normalized:
                normalized.append(clean)
        return normalized


class AgentSceneRelation(BaseModel):
    subject: str = Field(..., min_length=1, max_length=64)
    relation: str = Field(..., min_length=1, max_length=80)
    target: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=160)


class AgentSceneGraph(BaseModel):
    intent: str = Field("compose_scene", min_length=1, max_length=80)
    domain: str = Field("vector_canvas", min_length=1, max_length=80)
    summary: str = Field(..., min_length=1, max_length=200)
    canvas_width: int = Field(1024, ge=64, le=4096)
    canvas_height: int = Field(768, ge=64, le=4096)
    background: str | None = Field(default=None, max_length=64)
    objects: list[AgentSceneObject] = Field(default_factory=list, max_length=40)
    relations: list[AgentSceneRelation] = Field(default_factory=list, max_length=80)
    confidence: float = Field(0.72, ge=0, le=1)
    requires_confirmation: bool = False
    clarification_question: str | None = Field(default=None, max_length=240)
    risk_level: Literal["low", "medium", "high"] = "low"

    @field_validator("objects")
    @classmethod
    def require_unique_object_ids(cls, value: list[AgentSceneObject]) -> list[AgentSceneObject]:
        seen = set()
        for item in value:
            if item.object_id in seen:
                raise ValueError(f"重复的 scene object id: {item.object_id}")
            seen.add(item.object_id)
        return value
