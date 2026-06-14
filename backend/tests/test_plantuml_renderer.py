from __future__ import annotations

import pytest

from app import plantuml_renderer
from app.plantuml_renderer import PlantUMLRenderError, render_plantuml_source, validate_plantuml_source


def test_plantuml_renderer_returns_safe_fallback_svg_without_external_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.delenv("AI_PAINTING_PLANTUML_SERVER_URL", raising=False)
    monkeypatch.setattr(plantuml_renderer, "DEFAULT_BUNDLED_PLANTUML_JAR", tmp_path / "missing-plantuml.jar")

    result = render_plantuml_source("@startuml\nA --> B\n@enduml")

    assert result.mode == "fallback_local_svg"
    assert result.data_url.startswith("data:image/svg+xml;base64,")
    assert "<svg" in result.svg
    assert "A --&gt; B" in result.svg


def test_plantuml_source_validation_blocks_remote_includes() -> None:
    with pytest.raises(PlantUMLRenderError):
        validate_plantuml_source("@startuml\n!includeurl https://example.test/style.puml\nA --> B\n@enduml")


@pytest.mark.parametrize(
    "source",
    [
        "@startuml\nA --> B\n@endwbs",
        "@startuml\nA --> B\n@enduml\ntrailing text",
        "@startuml\nA --> B\n@enduml\n@startuml\nC --> D\n@enduml",
        "@startsalt\n{+\n  login\n}\n@endsalt",
    ],
)
def test_plantuml_source_validation_requires_single_matching_supported_block(source: str) -> None:
    with pytest.raises(PlantUMLRenderError):
        validate_plantuml_source(source)


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
        stdout = '<svg xmlns="http://www.w3.org/2000/svg" width="320px" height="160px" preserveAspectRatio="none"><text>ok</text></svg>'
        stderr = ""

    def fake_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        assert "-tsvg" in args[0]
        assert "-charset" in args[0]
        assert "UTF-8" in args[0]
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["input"].startswith("@startuml")
        return Completed()

    monkeypatch.setattr(plantuml_renderer.subprocess, "run", fake_run)

    result = render_plantuml_source("@startuml\nJar --> SVG\n@enduml")

    assert result.mode == "local_jar"
    assert "ok" in result.svg
    assert 'preserveAspectRatio="xMidYMid meet"' in result.svg
    assert result.width == 320
    assert result.height == 160


def test_plantuml_renderer_injects_default_font_for_chinese_diagrams(monkeypatch, tmp_path) -> None:
    jar_path = tmp_path / "plantuml.jar"
    jar_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("AI_PAINTING_PLANTUML_JAR", str(jar_path))
    monkeypatch.setenv("AI_PAINTING_PLANTUML_FONT_NAME", "Microsoft YaHei")
    monkeypatch.delenv("AI_PAINTING_PLANTUML_SERVER_URL", raising=False)
    captured_source: list[str] = []

    class Completed:
        returncode = 0
        stdout = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text>ok</text></svg>'
        stderr = ""

    def fake_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        captured_source.append(kwargs["input"])
        return Completed()

    monkeypatch.setattr(plantuml_renderer.subprocess, "run", fake_run)

    result = render_plantuml_source("@startuml\ntitle 图书馆\nA --> B\n@enduml")

    assert result.mode == "local_jar"
    assert captured_source[0].splitlines()[1] == "skinparam defaultFontName Microsoft YaHei"


def test_plantuml_renderer_uses_bundled_jar_by_default(monkeypatch, tmp_path) -> None:
    jar_path = tmp_path / "plantuml.jar"
    jar_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.delenv("AI_PAINTING_PLANTUML_SERVER_URL", raising=False)
    monkeypatch.setattr(plantuml_renderer, "DEFAULT_BUNDLED_PLANTUML_JAR", jar_path)

    class Completed:
        returncode = 0
        stdout = '<svg xmlns="http://www.w3.org/2000/svg"><text>bundled</text></svg>'
        stderr = ""

    def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        assert str(jar_path) in command
        assert kwargs["input"].startswith("@startuml")
        return Completed()

    monkeypatch.setattr(plantuml_renderer.subprocess, "run", fake_run)

    result = render_plantuml_source("@startuml\nBundled --> SVG\n@enduml")

    assert result.mode == "local_jar"
    assert "bundled" in result.svg


def test_plantuml_renderer_uses_server_when_configured(monkeypatch) -> None:
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.setenv("AI_PAINTING_PLANTUML_SERVER_URL", "https://plantuml.example.test/plantuml")
    monkeypatch.setattr(plantuml_renderer, "DEFAULT_BUNDLED_PLANTUML_JAR", plantuml_renderer.DEFAULT_BUNDLED_PLANTUML_JAR.with_name("missing.jar"))

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


def test_plantuml_renderer_falls_back_to_server_when_jar_fails(monkeypatch, tmp_path) -> None:
    jar_path = tmp_path / "plantuml.jar"
    jar_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("AI_PAINTING_PLANTUML_JAR", str(jar_path))
    monkeypatch.setenv("AI_PAINTING_PLANTUML_SERVER_URL", "https://plantuml.example.test")

    class Completed:
        returncode = 1
        stdout = ""
        stderr = "jar failed"

    class Response:
        text = '<svg xmlns="http://www.w3.org/2000/svg"><text>server-fallback</text></svg>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, timeout: float) -> Response:
        assert url.startswith("https://plantuml.example.test/svg/")
        assert timeout == 8.0
        return Response()

    monkeypatch.setattr(plantuml_renderer.subprocess, "run", lambda *args, **kwargs: Completed())
    monkeypatch.setattr(plantuml_renderer.httpx, "get", fake_get)

    result = render_plantuml_source("@startuml\nJar --> Server\n@enduml")

    assert result.mode == "server"
    assert "server-fallback" in result.svg


def test_plantuml_renderer_falls_back_to_server_when_java_is_unavailable(monkeypatch, tmp_path) -> None:
    jar_path = tmp_path / "plantuml.jar"
    jar_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("AI_PAINTING_PLANTUML_JAR", str(jar_path))
    monkeypatch.setenv("AI_PAINTING_PLANTUML_SERVER_URL", "https://plantuml.example.test")

    class Response:
        text = '<svg xmlns="http://www.w3.org/2000/svg"><text>server-after-java-error</text></svg>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, timeout: float) -> Response:
        assert url.startswith("https://plantuml.example.test/svg/")
        assert timeout == 8.0
        return Response()

    def fake_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise FileNotFoundError("java not found")

    monkeypatch.setattr(plantuml_renderer.subprocess, "run", fake_run)
    monkeypatch.setattr(plantuml_renderer.httpx, "get", fake_get)

    result = render_plantuml_source("@startuml\nJar --> Server\n@enduml")

    assert result.mode == "server"
    assert "server-after-java-error" in result.svg


def test_plantuml_renderer_caches_identical_server_source(monkeypatch) -> None:
    monkeypatch.delenv("AI_PAINTING_PLANTUML_JAR", raising=False)
    monkeypatch.setenv("AI_PAINTING_PLANTUML_SERVER_URL", "https://plantuml.example.test")
    monkeypatch.setattr(plantuml_renderer, "DEFAULT_BUNDLED_PLANTUML_JAR", plantuml_renderer.DEFAULT_BUNDLED_PLANTUML_JAR.with_name("missing.jar"))
    plantuml_renderer._render_plantuml_cached.cache_clear()
    calls: list[str] = []

    class Response:
        text = '<svg xmlns="http://www.w3.org/2000/svg"><text>cached-server</text></svg>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, *, timeout: float) -> Response:
        calls.append(url)
        assert timeout == 8.0
        return Response()

    monkeypatch.setattr(plantuml_renderer.httpx, "get", fake_get)

    source = "@startuml\nCached --> SVG\n@enduml"
    first = render_plantuml_source(source)
    second = render_plantuml_source(source)

    assert first.mode == "server"
    assert second.svg == first.svg
    assert len(calls) == 1
