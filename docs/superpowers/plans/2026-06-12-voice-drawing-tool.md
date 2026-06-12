# Voice Drawing Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-review MVP of a pure voice controlled drawing tool with a Python 3.12 backend, React frontend, and SQLite persistence.

**Architecture:** The frontend captures browser speech recognition text, renders vector drawing objects as SVG, and sends recognized commands to the backend. The backend normalizes Chinese drawing commands, creates executable operation plans, persists artwork state and operation logs in SQLite, and returns updated artwork snapshots. The first PR intentionally avoids authentication, paid ASR, and cloud storage.

**Tech Stack:** Python 3.12.10, FastAPI, SQLite, pytest, React, TypeScript, Vite, Web Speech API.

---

## File Structure

- `backend/requirements.txt`: backend runtime and test dependencies.
- `backend/app/main.py`: FastAPI app and API routes.
- `backend/app/database.py`: SQLite connection and schema initialization.
- `backend/app/repositories.py`: persistence helpers for artworks, drawing objects, operations, and voice logs.
- `backend/app/schemas.py`: Pydantic request and response models.
- `backend/app/command_parser.py`: Chinese voice command normalization, parsing, and planning.
- `backend/app/drawing_engine.py`: operation execution, inverse payload generation, undo, and redo.
- `backend/tests/test_command_parser.py`: parser unit tests.
- `backend/tests/test_api.py`: backend integration tests.
- `frontend/package.json`: React/Vite scripts and dependencies.
- `frontend/src/App.tsx`: voice-first application shell.
- `frontend/src/api.ts`: backend API client.
- `frontend/src/types.ts`: shared frontend types.
- `frontend/src/hooks/useVoiceRecognition.ts`: browser speech recognition adapter.
- `frontend/src/drawing/CanvasStage.tsx`: SVG canvas renderer.
- `frontend/src/utils/exportPng.ts`: frontend SVG-to-PNG export helper.
- `设计文档.md`: planned, implemented, and deferred command capabilities.
- `README.md`: Windows PowerShell development guide.

## Task 1: Backend Project Skeleton

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/database.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Add backend dependencies**

Create `backend/requirements.txt`:

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: Add SQLite schema initialization**

Create `backend/app/database.py` with `connect_db`, `init_db`, and `get_db`.

- [ ] **Step 3: Add Pydantic schemas**

Create `backend/app/schemas.py` with models for artworks, drawing objects, operations, command parse requests, and execution responses.

- [ ] **Step 4: Add FastAPI health route**

Create `backend/app/main.py` with `/health` returning `{"status": "ok"}` and startup database initialization.

- [ ] **Step 5: Run backend smoke test**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: tests pass after test files are created in later tasks.

## Task 2: Command Parser

**Files:**
- Create: `backend/app/command_parser.py`
- Create: `backend/tests/test_command_parser.py`

- [ ] **Step 1: Write parser tests**

Tests must cover:

```python
from app.command_parser import parse_command


def test_parse_create_canvas():
    plan = parse_command("新建一张横向白色画布")
    assert plan.operations[0].operation_type == "create_canvas"
    assert plan.operations[0].payload["background"] == "#ffffff"


def test_parse_circle_with_color_and_size():
    plan = parse_command("画一个蓝色圆形在中间 半径一百")
    op = plan.operations[0]
    assert op.operation_type == "add_object"
    assert op.payload["object"]["type"] == "circle"
    assert op.payload["object"]["style"]["fill"] == "#2563eb"
    assert op.payload["object"]["geometry"]["radius"] == 100


def test_parse_complex_house_plan():
    plan = parse_command("画一个房子 红色屋顶 蓝色门 两扇窗户")
    assert [op.payload["object"]["name"] for op in plan.operations] == ["房子主体", "红色屋顶", "蓝色门", "窗户1", "窗户2"]
```

- [ ] **Step 2: Implement normalization**

Implement Chinese number conversion for common values, synonym replacement for undo/redo/save/export, and color name mapping.

- [ ] **Step 3: Implement command planning**

Return operation plans for create canvas, add shapes, edit latest object color, move latest object, undo, redo, save, export PNG, and the house complex command.

- [ ] **Step 4: Run parser tests**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/test_command_parser.py -q`

Expected: all parser tests pass.

## Task 3: Drawing Engine And API

**Files:**
- Create: `backend/app/repositories.py`
- Create: `backend/app/drawing_engine.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Write API integration tests**

Tests must cover create artwork, submit a text command, confirm an object is persisted, and undo the last operation.

- [ ] **Step 2: Implement repositories**

Persist artworks, current drawing objects, operations, redo status, and voice command logs using SQLite with foreign keys enabled.

- [ ] **Step 3: Implement operation execution**

Support `create_canvas`, `add_object`, `update_object`, `move_object`, `set_style`, `save_artwork`, `export_artwork`, `undo`, and `redo`.

- [ ] **Step 4: Implement API routes**

Add:

```txt
POST /api/artworks
GET /api/artworks
GET /api/artworks/{artwork_id}
POST /api/commands/parse
POST /api/artworks/{artwork_id}/commands
POST /api/artworks/{artwork_id}/undo
POST /api/artworks/{artwork_id}/redo
```

- [ ] **Step 5: Run backend tests**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: all backend tests pass.

## Task 4: React Voice-First Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/hooks/useVoiceRecognition.ts`
- Create: `frontend/src/drawing/CanvasStage.tsx`
- Create: `frontend/src/utils/exportPng.ts`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Add React/Vite configuration**

Use a minimal React TypeScript Vite setup with scripts `dev`, `build`, and `preview`.

- [ ] **Step 2: Add API client**

Implement functions for creating artwork, fetching artwork, submitting commands, undo, and redo.

- [ ] **Step 3: Add voice recognition hook**

Use `window.SpeechRecognition || window.webkitSpeechRecognition`, set `lang` to `zh-CN`, and expose status, transcript, support detection, and restart behavior.

- [ ] **Step 4: Add SVG canvas renderer**

Render persisted objects for rectangle, circle, ellipse, triangle, line, arrow, star, and text.

- [ ] **Step 5: Add voice-first app shell**

The first screen must be the drawing workspace. It should auto-attempt voice listening, display status, submit final transcripts, and provide no mouse or keyboard drawing path.

- [ ] **Step 6: Run frontend build**

Run: `npm run build --prefix frontend`

Expected: Vite build completes successfully.

## Task 5: Documentation

**Files:**
- Modify: `README.md`
- Create: `设计文档.md`
- Modify: `需求文档.md` only if implementation scope requires correction.

- [ ] **Step 1: Write README**

Document Windows PowerShell setup, Python virtual environment, backend install, frontend install, dev commands, build commands, test commands, environment variables, project structure, and known browser speech limitations.

- [ ] **Step 2: Write design document**

Record planned commands, implemented commands, deferred commands with reasons, speech recognition approach, command parser architecture, latency strategy, SQLite schema, API routes, test results, and unverified items.

- [ ] **Step 3: Check docs against implementation**

Run: `Get-Content -LiteralPath '.\README.md' -Encoding UTF8 -TotalCount 80`

Expected: README describes only implemented or clearly marked planned features.

## Task 6: Verification, Commit, Push, PR

**Files:**
- All created files.

- [ ] **Step 1: Run backend tests**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: all tests pass.

- [ ] **Step 2: Run frontend build**

Run: `npm run build --prefix frontend`

Expected: build succeeds.

- [ ] **Step 3: Check Git diff**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 4: Commit**

Run:

```powershell
git add .
git commit -m "初始化纯语音绘图工具"
```

- [ ] **Step 5: Push**

Run: `git push -u origin codex/AI-Painting`

- [ ] **Step 6: Create PR**

Use `gh pr create` with a Chinese title and a description containing modification content, reason, key files, checks, check results, known risks, screenshots or recording status, and follow-up suggestions.
