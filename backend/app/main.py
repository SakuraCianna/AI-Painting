from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlite3 import Connection

from .command_parser import parse_command
from .database import get_db, init_db
from .drawing_engine import apply_operation, apply_operation_plan, redo_last_operation, undo_last_operation
from .repositories import create_artwork, get_artwork, list_artworks, record_voice_log
from .schemas import (
    ArtworkCreateRequest,
    ArtworkResponse,
    CommandExecutionResponse,
    CommandParseRequest,
    CommandPlan,
    OperationResponse,
)


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
def api_parse_command(request: CommandParseRequest) -> CommandPlan:
    return parse_command(request.text)


@app.post("/api/artworks/{artwork_id}/commands", response_model=CommandExecutionResponse)
def api_execute_command(
    artwork_id: str,
    request: CommandParseRequest,
    db: Connection = Depends(get_db),
) -> CommandExecutionResponse:
    started_at = perf_counter()
    try:
        get_artwork(db, artwork_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    plan = parse_command(request.text)
    parse_finished_at = perf_counter()

    if plan.requires_confirmation:
        record_voice_log(
            db,
            artwork_id=artwork_id,
            raw_transcript=request.text,
            normalized_text=plan.normalized_text,
            parse_result=plan.model_dump(),
            confidence=plan.confidence,
            status="needs_confirmation",
            error_message=plan.clarification_question,
            latency={"parse_ms": round((parse_finished_at - started_at) * 1000, 2)},
        )
        return CommandExecutionResponse(message=plan.clarification_question or "需要确认", plan=plan, artwork=get_artwork(db, artwork_id))

    message = "未执行任何操作"
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
    record_voice_log(
        db,
        artwork_id=artwork_id,
        raw_transcript=request.text,
        normalized_text=plan.normalized_text,
        parse_result=plan.model_dump(),
        confidence=plan.confidence,
        status=status,
        error_message=error_message,
        latency={
            "parse_ms": round((parse_finished_at - started_at) * 1000, 2),
            "execute_ms": round((finished_at - parse_finished_at) * 1000, 2),
            "total_ms": round((finished_at - started_at) * 1000, 2),
        },
    )
    if status == "failed":
        raise HTTPException(status_code=422, detail=message)
    return CommandExecutionResponse(message=message, plan=plan, artwork=artwork)


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
