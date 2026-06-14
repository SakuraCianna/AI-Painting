from __future__ import annotations

import pytest

from app import plantuml_renderer
from app.plantuml_renderer import PlantUMLRenderError, render_plantuml_source, validate_plantuml_source


def test_plantuml_renderer_returns_safe_fallback_svg_without_external_runtime(monkeypatch) -> None:
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.delenv("AI_PAINTING_PLANTUML_SERVER_URL", raising=False)

    result = render_plantuml_source("@startuml\nA --> B\n@enduml")

    assert result.mode == "fallback_local_svg"
    assert result.data_url.startswith("data:image/svg+xml;base64,")
    assert "<svg" in result.svg
    assert "A --&gt; B" in result.svg


def test_plantuml_source_validation_blocks_remote_includes() -> None:
    with pytest.raises(PlantUMLRenderError):
        validate_plantuml_source("@startuml\n!includeurl https://example.test/style.puml\nA --> B\n@enduml")


def test_plantuml_source_validation_rejects_invalid_or_oversized_source(monkeypatch) -> None:
    with pytest.raises(PlantUMLRenderError):
        validate_plantuml_source("A --> B")

    monkeypatch.setenv("AI_PAINTING_PLANTUML_MAX_SOURCE_CHARS", "20")
    long_body = "A --> B\n" * 200
    with pytest.raises(PlantUMLRenderError):
        validate_plantuml_source(f"@startuml\n{long_body}@enduml")


def test_plantuml_renderer_uses_local_jar_when_configured(monkeypatch, tmp_path) -> None:
    jar_path = tmp_path / "plantuml.jar"
    jar_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("AI_PAINTING_PLANTUML_JAR", str(jar_path))
    monkeypatch.delenv("AI_PAINTING_PLANTUML_SERVER_URL", raising=False)

    class Completed:
        returncode = 0
        stdout = '<svg xmlns="http://www.w3.org/2000/svg"><text>ok</text></svg>'
        stderr = ""

    def fake_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        assert "-tsvg" in args[0]
        assert kwargs["input"].startswith("@startuml")
        return Completed()

    monkeypatch.setattr(plantuml_renderer.subprocess, "run", fake_run)

    result = render_plantuml_source("@startuml\nJar --> SVG\n@enduml")

    assert result.mode == "local_jar"
    assert "ok" in result.svg


def test_plantuml_renderer_uses_server_when_configured(monkeypatch) -> None:
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.setenv("AI_PAINTING_PLANTUML_SERVER_URL", "https://plantuml.example.test/plantuml")

    class Response:
        text = '<svg xmlns="http://www.w3.org/2000/svg"><text>server</text></svg>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, timeout: float):  # noqa: ANN201
        assert url.startswith("https://plantuml.example.test/plantuml/svg/")
        assert timeout == 8.0
        return Response()

    monkeypatch.setattr(plantuml_renderer.httpx, "get", fake_get)

    result = render_plantuml_source("@startuml\nServer --> SVG\n@enduml")

    assert result.mode == "server"
    assert "server" in result.svg
