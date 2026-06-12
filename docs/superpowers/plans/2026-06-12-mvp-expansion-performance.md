# MVP Expansion And Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the MVP with batch voice commands, richer feedback, and safer faster command execution.

**Architecture:** Keep the current FastAPI + SQLite + React split. Extend the rule parser with high-value complex commands, add batch operation execution in the drawing engine, and show command plan feedback in the React workspace.

**Tech Stack:** Python 3.12.10, FastAPI, SQLite, pytest, React, TypeScript, Vite, Web Speech API, browser speech synthesis.

---

## File Structure

- `backend/app/command_parser.py`: add multi-star, batch recolor, batch move, and scale parsing.
- `backend/app/drawing_engine.py`: add batch style, batch move, scale, and plan-level commit/rollback.
- `backend/app/repositories.py`: add selector-based object lookup and commit control for transaction batching.
- `backend/app/database.py`: add indexes for drawing objects, operations, and voice logs.
- `backend/app/main.py`: execute multi-step plans through the new plan executor.
- `backend/tests/test_command_parser.py`: cover new parser abilities.
- `backend/tests/test_api.py`: cover batch execution, undo, and scale.
- `frontend/src/App.tsx`: show latest execution plan and speak command results.
- `frontend/src/styles.css`: style plan feedback.
- `README.md`: document new capabilities.
- `设计文档.md`: record implemented expansion and remaining risks.

## Task 1: Batch Command Parsing

- [x] Support “画三颗黄色星星 从左到右变小”.
- [x] Support “把所有蓝色图形改成绿色 然后整体向上移动一点”.
- [x] Support “把它放大一倍”.
- [x] Add parser tests for each command.

## Task 2: Batch Execution And Undo

- [x] Add selector-based object lookup.
- [x] Add `set_style_many`.
- [x] Add `move_many`.
- [x] Add `scale_object`.
- [x] Preserve undo and redo behavior for batch operations.
- [x] Add API tests for batch recolor, movement, undo, and scale.

## Task 3: Performance Improvements

- [x] Add SQLite indexes for object, operation, and voice log lookups.
- [x] Execute multi-step plans with a single redo-stack clear and one final commit.
- [x] Roll back the full plan if any step fails.
- [x] Make operation undo order deterministic with `created_at DESC, rowid DESC`.

## Task 4: Frontend Feedback

- [x] Show latest execution plan with step count and confidence.
- [x] Show Chinese operation labels instead of raw operation identifiers.
- [x] Use browser speech synthesis to announce command results.
- [x] Keep the UI voice-first, without mouse or keyboard drawing controls.

## Task 5: Verification

- [x] Run backend tests.
- [x] Run frontend build.
- [x] Run Git whitespace check.
- [x] Refresh workspace screenshot.
