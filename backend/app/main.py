from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlite3 import Connection

from .asr import AsrProvidersUnavailable, get_asr_provider_status, transcribe_audio_data_url
from .command_parser import normalize_text, parse_command
from .config import load_env_file
from .database import get_db, init_db
from .drawing_engine import apply_operation, apply_operation_plan, redo_last_operation, undo_last_operation
from .llm_planner import LlmPlannerError, plan_with_mimo, should_use_llm_planner
from .repositories import (
    create_artwork,
    get_artwork,
    get_latest_voice_log_by_status,
    list_artworks,
    mark_voice_log_status,
    record_voice_log,
)
from .schemas import (
    AsrProvidersResponse,
    AsrTranscriptionRequest,
    AsrTranscriptionResponse,
    ArtworkCreateRequest,
    ArtworkResponse,
    CommandExecutionMetrics,
    CommandExecutionResponse,
    CommandParseRequest,
    CommandPlan,
    OperationResponse,
    TtsSynthesisRequest,
    TtsSynthesisResponse,
)
from .tts import TtsProviderError, synthesize_with_xiaomi


load_env_file()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Painting Voice Drawing API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass(frozen=True)
class PlannedCommand:
    plan: CommandPlan
    metrics: CommandExecutionMetrics


@dataclass(frozen=True)
class ConfirmationCommand:
    plan: CommandPlan
    metrics: CommandExecutionMetrics
    pending_log_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/artworks", response_model=ArtworkResponse)
def api_create_artwork(request: ArtworkCreateRequest, db: Connection = Depends(get_db)) -> ArtworkResponse:
    return create_artwork(db, request)


@app.get("/api/artworks", response_model=list[ArtworkResponse])
def api_list_artworks(db: Connection = Depends(get_db)) -> list[ArtworkResponse]:
    return list_artworks(db)


@app.get("/api/artworks/{artwork_id}", response_model=ArtworkResponse)
def api_get_artwork(artwork_id: str, db: Connection = Depends(get_db)) -> ArtworkResponse:
    try:
        return get_artwork(db, artwork_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/commands/parse", response_model=CommandPlan)
async def api_parse_command(request: CommandParseRequest) -> CommandPlan:
    return await build_command_plan(request.text)


def _default_plan_explanation(plan: CommandPlan) -> str:
    if plan.requires_confirmation and plan.clarification_question:
        return plan.clarification_question
    if plan.scene_plan and plan.scene_plan.summary:
        return plan.scene_plan.summary
    if plan.operations:
        return f"准备执行 {len(plan.operations)} 个绘图步骤"
    return "没有生成可执行绘图步骤"


def _with_plan_metadata(plan: CommandPlan, planner_source: str) -> CommandPlan:
    plan.planner_source = planner_source
    if not plan.explanation:
        plan.explanation = _default_plan_explanation(plan)
    return plan


async def build_command_plan(text: str) -> CommandPlan:
    return (await build_command_plan_with_metrics(text)).plan


async def build_command_plan_with_metrics(text: str) -> PlannedCommand:
    started_at = perf_counter()
    rule_started_at = perf_counter()
    rule_plan = _with_plan_metadata(parse_command(text), "rules")
    rule_finished_at = perf_counter()
    metrics = CommandExecutionMetrics(
        rule_parse_ms=round((rule_finished_at - rule_started_at) * 1000, 2),
        planner_source=rule_plan.planner_source,
    )
    if not should_use_llm_planner(text, rule_plan):
        metrics.planner_total_ms = round((rule_finished_at - started_at) * 1000, 2)
        return PlannedCommand(rule_plan, metrics)

    metrics.llm_attempted = True
    llm_started_at = perf_counter()
    try:
        plan = _with_plan_metadata(await plan_with_mimo(text), "mimo")
        llm_finished_at = perf_counter()
        metrics.llm_planner_ms = round((llm_finished_at - llm_started_at) * 1000, 2)
        metrics.planner_total_ms = round((llm_finished_at - started_at) * 1000, 2)
        metrics.llm_succeeded = True
        metrics.planner_source = plan.planner_source
        return PlannedCommand(plan, metrics)
    except LlmPlannerError:
        llm_finished_at = perf_counter()
        plan = _with_plan_metadata(rule_plan, "rules_fallback")
        metrics.llm_planner_ms = round((llm_finished_at - llm_started_at) * 1000, 2)
        metrics.planner_total_ms = round((llm_finished_at - started_at) * 1000, 2)
        metrics.fallback_used = True
        metrics.planner_source = plan.planner_source
        return PlannedCommand(plan, metrics)


def _is_confirmation_text(text: str) -> bool:
    normalized = normalize_text(text)
    if any(keyword in normalized for keyword in ("取消", "不要", "不用", "别")):
        return False
    return any(keyword in normalized for keyword in ("确认", "确定", "可以", "执行", "是的", "对的"))


def _is_cancel_confirmation_text(text: str) -> bool:
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in ("取消", "不要", "不用", "别清空", "不清空", "算了"))


def _latest_pending_clear_canvas(db: Connection, artwork_id: str) -> tuple[str, CommandPlan] | None:
    row = get_latest_voice_log_by_status(db, artwork_id, "needs_confirmation")
    if row is None:
        return None
    try:
        plan = CommandPlan.model_validate(json.loads(row["parse_result_json"]))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if len(plan.operations) != 1 or plan.operations[0].operation_type != "clear_canvas":
        return None
    return str(row["id"]), plan


def _confirmed_clear_canvas_command(text: str, pending_log_id: str, pending_plan: CommandPlan) -> ConfirmationCommand:
    plan = pending_plan.model_copy(deep=True)
    plan.raw_text = text
    plan.normalized_text = normalize_text(text)
    plan.requires_confirmation = False
    plan.clarification_question = None
    plan.explanation = "已确认执行清空画布"
    plan.planner_source = "confirmation"
    metrics = CommandExecutionMetrics(
        rule_parse_ms=0,
        planner_total_ms=0,
        planner_source="confirmation",
    )
    return ConfirmationCommand(plan=plan, metrics=metrics, pending_log_id=pending_log_id)


@app.get("/api/asr/providers", response_model=AsrProvidersResponse)
def api_get_asr_providers() -> AsrProvidersResponse:
    return get_asr_provider_status()


@app.post("/api/asr/transcribe", response_model=AsrTranscriptionResponse)
async def api_transcribe_audio(request: AsrTranscriptionRequest) -> AsrTranscriptionResponse:
    try:
        return await transcribe_audio_data_url(request.audio_data_url, request.language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AsrProvidersUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "后端 ASR 不可用, 请使用 Web Speech API 兜底",
                "attempts": [attempt.model_dump() for attempt in exc.attempts],
            },
        ) from exc


@app.post("/api/tts/synthesize", response_model=TtsSynthesisResponse)
async def api_synthesize_speech(request: TtsSynthesisRequest) -> TtsSynthesisResponse:
    try:
        return await synthesize_with_xiaomi(request.text, request.voice, request.style)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TtsProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/artworks/{artwork_id}/commands", response_model=CommandExecutionResponse)
async def api_execute_command(
    artwork_id: str,
    request: CommandParseRequest,
    db: Connection = Depends(get_db),
) -> CommandExecutionResponse:
    started_at = perf_counter()
    try:
        get_artwork(db, artwork_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    pending_clear = _latest_pending_clear_canvas(db, artwork_id)
    pending_confirmation_id: str | None = None

    if pending_clear and _is_cancel_confirmation_text(request.text):
        pending_log_id, pending_plan = pending_clear
        mark_voice_log_status(db, pending_log_id, "canceled", error_message="用户取消清空画布")
        plan = CommandPlan(
            raw_text=request.text,
            normalized_text=normalize_text(request.text),
            operations=[],
            confidence=pending_plan.confidence,
            requires_confirmation=False,
            risk_level="low",
            explanation="已取消清空画布",
            planner_source="confirmation",
        )
        metrics = CommandExecutionMetrics(
            rule_parse_ms=0,
            planner_total_ms=0,
            execute_ms=0,
            total_ms=round((perf_counter() - started_at) * 1000, 2),
            planner_source="confirmation",
        )
        record_voice_log(
            db,
            artwork_id=artwork_id,
            raw_transcript=request.text,
            normalized_text=plan.normalized_text,
            parse_result=plan.model_dump(),
            confidence=plan.confidence,
            status="canceled",
            error_message=None,
            latency=metrics.model_dump(exclude_none=True),
        )
        return CommandExecutionResponse(message="已取消清空画布", plan=plan, artwork=get_artwork(db, artwork_id), metrics=metrics)

    if pending_clear and _is_confirmation_text(request.text):
        pending_log_id, pending_plan = pending_clear
        confirmation_command = _confirmed_clear_canvas_command(request.text, pending_log_id, pending_plan)
        plan = confirmation_command.plan
        metrics = confirmation_command.metrics
        pending_confirmation_id = confirmation_command.pending_log_id
    else:
        planned_command = await build_command_plan_with_metrics(request.text)
        plan = planned_command.plan
        metrics = planned_command.metrics

    if plan.requires_confirmation:
        metrics.execute_ms = 0
        metrics.total_ms = round((perf_counter() - started_at) * 1000, 2)
        record_voice_log(
            db,
            artwork_id=artwork_id,
            raw_transcript=request.text,
            normalized_text=plan.normalized_text,
            parse_result=plan.model_dump(),
            confidence=plan.confidence,
            status="needs_confirmation",
            error_message=plan.clarification_question,
            latency=metrics.model_dump(exclude_none=True),
        )
        return CommandExecutionResponse(
            message=plan.clarification_question or "需要确认",
            plan=plan,
            artwork=get_artwork(db, artwork_id),
            metrics=metrics,
        )

    message = "未执行任何操作"
    execute_started_at = perf_counter()
    try:
        if len(plan.operations) == 1 and plan.operations[0].operation_type == "undo":
            undo_last_operation(db, artwork_id)
            message = "已撤销上一步"
        elif len(plan.operations) == 1 and plan.operations[0].operation_type == "redo":
            redo_last_operation(db, artwork_id)
            message = "已恢复上一步"
        elif len(plan.operations) == 1:
            message = apply_operation(db, artwork_id, plan.operations[0])
        else:
            message = apply_operation_plan(db, artwork_id, plan.operations)
        artwork = get_artwork(db, artwork_id)
        status = "success"
        error_message = None
    except (KeyError, ValueError) as exc:
        artwork = get_artwork(db, artwork_id)
        status = "failed"
        error_message = str(exc)
        message = str(exc)

    finished_at = perf_counter()
    metrics.execute_ms = round((finished_at - execute_started_at) * 1000, 2)
    metrics.total_ms = round((finished_at - started_at) * 1000, 2)
    if pending_confirmation_id:
        mark_voice_log_status(
            db,
            pending_confirmation_id,
            "confirmed" if status == "success" else "confirmation_failed",
            error_message="用户已确认执行" if status == "success" else message,
        )
    record_voice_log(
        db,
        artwork_id=artwork_id,
        raw_transcript=request.text,
        normalized_text=plan.normalized_text,
        parse_result=plan.model_dump(),
        confidence=plan.confidence,
        status=status,
        error_message=error_message,
        latency=metrics.model_dump(exclude_none=True),
    )
    if status == "failed":
        raise HTTPException(status_code=422, detail=message)
    return CommandExecutionResponse(message=message, plan=plan, artwork=artwork, metrics=metrics)


@app.post("/api/artworks/{artwork_id}/undo", response_model=OperationResponse)
def api_undo(artwork_id: str, db: Connection = Depends(get_db)) -> OperationResponse:
    try:
        artwork = undo_last_operation(db, artwork_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OperationResponse(message="已撤销上一步", artwork=artwork)


@app.post("/api/artworks/{artwork_id}/redo", response_model=OperationResponse)
def api_redo(artwork_id: str, db: Connection = Depends(get_db)) -> OperationResponse:
    try:
        artwork = redo_last_operation(db, artwork_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OperationResponse(message="已恢复上一步", artwork=artwork)
