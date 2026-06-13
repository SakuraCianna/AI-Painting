from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_python_quality_tooling_is_configured() -> None:
    pyproject = ROOT / "pyproject.toml"
    pre_commit = ROOT / ".pre-commit-config.yaml"

    assert pyproject.exists()
    pyproject_text = pyproject.read_text(encoding="utf-8")
    assert "[tool.ruff]" in pyproject_text
    assert "[tool.mypy]" in pyproject_text

    assert pre_commit.exists()
    pre_commit_text = pre_commit.read_text(encoding="utf-8")
    assert "ruff-pre-commit" in pre_commit_text
    assert "pre-commit/mirrors-mypy" in pre_commit_text


def test_ci_runs_static_quality_gates() -> None:
    workflow = ROOT / ".github" / "workflows" / "ai-painting-ci.yml"
    workflow_text = workflow.read_text(encoding="utf-8")

    assert "backend/requirements-dev.txt" in workflow_text
    assert "ruff check" in workflow_text
    assert "mypy" in workflow_text
    assert "pre-commit run --all-files" in workflow_text
