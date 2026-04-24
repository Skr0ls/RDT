"""
Smoke / functional tests for ArtifactPipeline (core-hardening M1-M3).

Covers:
- successful generation for nginx-proxy, nginx-static, nginx-spa (TEMPLATE)
- ArtifactSourceType.STATIC and ArtifactSourceType.PYTHON
- ArtifactContext.as_template_vars()
- SKIP policy (existing file is not overwritten)
- OVERWRITE policy (existing file is overwritten)
- ERROR_IF_EXISTS policy (error when the file already exists)
- preflight: missing template detection
- preflight: ERROR_IF_EXISTS conflict detection
- preflight: STATIC without static_content detection
- preflight: PYTHON without renderer detection
- preflight: successful pass without issues
- has_errors() helper
- correct behavior with non-standard project_root (similar to --file)
- failure on template error (missing template)
- plan→apply split
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rdt.artifacts import (
    ArtifactContext,
    ArtifactDef,
    ArtifactPipeline,
    ArtifactResult,
    ArtifactSourceType,
    OverwritePolicy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NGINX_ANSWERS = {
    "nginx_upstream": "app:8000",
    "nginx_server_name": "localhost",
    "nginx_config_dir": "./nginx",
    "nginx_html_dir": "./nginx/html",
}


def _make_context(
    base_dir: Path,
    answers: dict | None = None,
    service_name: str = "nginx-proxy",
) -> ArtifactContext:
    return ArtifactContext(
        service_name=service_name,
        answers=answers or NGINX_ANSWERS,
        env_values={},
        project_root=base_dir,
        compose_file=base_dir / "docker-compose.yml",
        preset=None,
    )


def _make_pipeline(
    artifacts: list[ArtifactDef],
    base_dir: Path,
    answers: dict | None = None,
) -> ArtifactPipeline:
    return ArtifactPipeline(
        artifacts=artifacts,
        context=_make_context(base_dir, answers),
    )


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------

def test_nginx_proxy_created(tmp_path: Path) -> None:
    """Pipeline creates nginx/nginx.conf for nginx-proxy."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    results = pipeline.run()

    assert len(results) == 1
    r = results[0]
    assert r.status == "created"
    assert r.path.exists()
    content = r.path.read_text()
    assert "app:8000" in content
    assert "localhost" in content


def test_nginx_static_created(tmp_path: Path) -> None:
    """Pipeline creates nginx/nginx.conf for nginx-static."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-static.conf.j2",
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "created"
    assert results[0].path.exists()


def test_nginx_spa_created(tmp_path: Path) -> None:
    """Pipeline creates nginx/nginx.conf for nginx-spa."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-spa.conf.j2",
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "created"
    assert results[0].path.exists()


# ---------------------------------------------------------------------------
# Overwrite policies
# ---------------------------------------------------------------------------

def test_skip_existing_file(tmp_path: Path) -> None:
    """SKIP: an existing file is not overwritten."""
    target = tmp_path / "nginx" / "nginx.conf"
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL", encoding="utf-8")

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
        overwrite=OverwritePolicy.SKIP,
    )
    results = _make_pipeline([artifact], tmp_path).run()

    assert results[0].status == "skipped"
    assert target.read_text() == "ORIGINAL"


def test_overwrite_existing_file(tmp_path: Path) -> None:
    """OVERWRITE: an existing file is overwritten."""
    target = tmp_path / "nginx" / "nginx.conf"
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL", encoding="utf-8")

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
        overwrite=OverwritePolicy.OVERWRITE,
    )
    results = _make_pipeline([artifact], tmp_path).run()

    assert results[0].status == "overwritten"
    assert "ORIGINAL" not in target.read_text()


def test_error_if_exists_policy(tmp_path: Path) -> None:
    """ERROR_IF_EXISTS: returns an error when the file already exists."""
    target = tmp_path / "nginx" / "nginx.conf"
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL", encoding="utf-8")

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
        overwrite=OverwritePolicy.ERROR_IF_EXISTS,
    )
    results = _make_pipeline([artifact], tmp_path).run()

    assert results[0].status == "error"
    assert results[0].error is not None
    # The file must not be changed.
    assert target.read_text() == "ORIGINAL"




# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def test_preflight_ok(tmp_path: Path) -> None:
    """Preflight returns no issues for a valid artifact."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert issues == []


def test_preflight_catches_missing_template(tmp_path: Path) -> None:
    """Preflight detects a missing template."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/DOES_NOT_EXIST.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert len(issues) == 1
    assert "DOES_NOT_EXIST" in issues[0].reason


def test_preflight_catches_error_if_exists(tmp_path: Path) -> None:
    """Preflight detects an ERROR_IF_EXISTS conflict before writing."""
    target = tmp_path / "nginx" / "nginx.conf"
    target.parent.mkdir(parents=True)
    target.write_text("EXISTS", encoding="utf-8")

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
        overwrite=OverwritePolicy.ERROR_IF_EXISTS,
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert len(issues) == 1


def test_preflight_skips_inactive_conditions(tmp_path: Path) -> None:
    """Preflight skips artifacts whose condition is not met."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/DOES_NOT_EXIST.conf.j2",
        condition="generate_nginx",  # key is missing from answers
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert issues == []  # condition is not met → artifact is inactive, no issues


# ---------------------------------------------------------------------------
# Failure on template error
# ---------------------------------------------------------------------------

def test_missing_template_returns_error(tmp_path: Path) -> None:
    """Missing template → status 'error', not an exception."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/DOES_NOT_EXIST.conf.j2",
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "error"
    assert results[0].error is not None


# ---------------------------------------------------------------------------
# has_errors helper
# ---------------------------------------------------------------------------

def test_has_errors_true() -> None:
    """has_errors returns True when there is at least one error."""
    results = [
        ArtifactResult(path=Path("a"), status="created"),
        ArtifactResult(path=Path("b"), status="error", error="oops"),
    ]
    assert ArtifactPipeline.has_errors(results) is True


def test_has_errors_false() -> None:
    """has_errors returns False when there are no errors."""
    results = [
        ArtifactResult(path=Path("a"), status="created"),
        ArtifactResult(path=Path("b"), status="skipped"),
    ]
    assert ArtifactPipeline.has_errors(results) is False


# ---------------------------------------------------------------------------
# Behavior with non-standard base_dir (similar to --file)
# ---------------------------------------------------------------------------

def test_custom_base_dir(tmp_path: Path) -> None:
    """Artifacts are generated relative to the provided base_dir."""
    custom_root = tmp_path / "infra"
    custom_root.mkdir()

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    results = _make_pipeline([artifact], custom_root).run()

    assert results[0].status == "created"
    expected = custom_root / "nginx" / "nginx.conf"
    assert expected.exists()
    # The file must not appear directly under tmp_path.
    assert not (tmp_path / "nginx" / "nginx.conf").exists()


# ---------------------------------------------------------------------------
# Test _resolve_project_root from cli
# ---------------------------------------------------------------------------

def test_resolve_project_root_default() -> None:
    """For docker-compose.yml in cwd, root == cwd."""
    from rdt.cli import _resolve_project_root
    result = _resolve_project_root(Path("docker-compose.yml"))
    assert result == Path.cwd().resolve()


def test_resolve_project_root_subdir(tmp_path: Path) -> None:
    """For a file in a subdirectory, root == that subdirectory."""
    from rdt.cli import _resolve_project_root
    compose = tmp_path / "infra" / "docker-compose.yml"
    result = _resolve_project_root(compose)
    assert result == (tmp_path / "infra").resolve()


def test_find_existing_compose_file_prefers_common_order(tmp_path: Path) -> None:
    """Existing Compose files are detected using common filename conventions."""
    from rdt.yaml_manager import find_existing_compose_file

    (tmp_path / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")

    assert find_existing_compose_file(tmp_path) == tmp_path / "compose.yml"


def test_resolve_default_compose_file_uses_existing_compose_yaml(tmp_path: Path) -> None:
    """The default docker-compose.yml path resolves to an existing compose.yaml."""
    from rdt.yaml_manager import resolve_default_compose_file

    existing = tmp_path / "compose.yaml"
    existing.write_text("services: {}\n", encoding="utf-8")

    assert resolve_default_compose_file(tmp_path / "docker-compose.yml") == existing


def test_resolve_default_compose_file_keeps_custom_path(tmp_path: Path) -> None:
    """Custom compose paths are not replaced by common filename discovery."""
    from rdt.yaml_manager import resolve_default_compose_file

    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    custom = tmp_path / "custom-compose.yml"

    assert resolve_default_compose_file(custom) == custom


def test_cli_add_uses_existing_compose_yml_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rdt add --yes updates compose.yml instead of creating docker-compose.yml."""
    from typer.testing import CliRunner
    from rdt.cli import app

    monkeypatch.chdir(tmp_path)
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["add", "redis", "--yes"])

    assert result.exit_code == 0, result.output
    assert "redis:" in compose.read_text(encoding="utf-8")
    assert not (tmp_path / "docker-compose.yml").exists()



# ---------------------------------------------------------------------------
# ArtifactContext
# ---------------------------------------------------------------------------

def test_artifact_context_as_template_vars(tmp_path: Path) -> None:
    """as_template_vars() includes answers plus service fields."""
    ctx = ArtifactContext(
        service_name="my-svc",
        answers={"foo": "bar"},
        env_values={"DB_PASS": "secret"},
        project_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        preset=None,
    )
    tvars = ctx.as_template_vars()
    assert tvars["foo"] == "bar"
    assert tvars["service_name"] == "my-svc"
    assert tvars["project_root"] == str(tmp_path)
    assert tvars["env_values"] == {"DB_PASS": "secret"}


def test_artifact_context_with_preset(tmp_path: Path) -> None:
    """as_template_vars() includes preset_name and preset_display_name when preset is set."""
    class _FakePreset:
        name = "nginx-proxy"
        display_name = "Nginx Proxy"

    ctx = ArtifactContext(
        service_name="nginx-proxy",
        answers={},
        env_values={},
        project_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        preset=_FakePreset(),
    )
    tvars = ctx.as_template_vars()
    assert tvars["preset_name"] == "nginx-proxy"
    assert tvars["preset_display_name"] == "Nginx Proxy"


# ---------------------------------------------------------------------------
# ArtifactSourceType.STATIC
# ---------------------------------------------------------------------------

def test_static_source_creates_file(tmp_path: Path) -> None:
    """STATIC: writes static_content to the target file."""
    artifact = ArtifactDef(
        relative_path="config/app.conf",
        source_type=ArtifactSourceType.STATIC,
        static_content="# static config\nkey=value\n",
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "created"
    content = (tmp_path / "config" / "app.conf").read_text()
    assert "key=value" in content


def test_preflight_catches_static_without_content(tmp_path: Path) -> None:
    """Preflight detects STATIC without static_content."""
    artifact = ArtifactDef(
        relative_path="config/app.conf",
        source_type=ArtifactSourceType.STATIC,
        static_content=None,
    )
    issues = _make_pipeline([artifact], tmp_path).preflight()
    assert len(issues) == 1
    assert "STATIC" in issues[0].reason


# ---------------------------------------------------------------------------
# ArtifactSourceType.PYTHON
# ---------------------------------------------------------------------------

def test_python_source_creates_file(tmp_path: Path) -> None:
    """PYTHON: calls renderer(context) and writes the result."""
    def my_renderer(ctx: ArtifactContext) -> str:
        return f"# Generated for {ctx.service_name}\nupstream={ctx.answers.get('nginx_upstream')}\n"

    artifact = ArtifactDef(
        relative_path="config/dynamic.conf",
        source_type=ArtifactSourceType.PYTHON,
        renderer=my_renderer,
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "created"
    content = (tmp_path / "config" / "dynamic.conf").read_text()
    assert "nginx-proxy" in content
    assert "app:8000" in content


def test_preflight_catches_python_without_renderer(tmp_path: Path) -> None:
    """Preflight detects PYTHON without renderer."""
    artifact = ArtifactDef(
        relative_path="config/dynamic.conf",
        source_type=ArtifactSourceType.PYTHON,
        renderer=None,
    )
    issues = _make_pipeline([artifact], tmp_path).preflight()
    assert len(issues) == 1
    assert "PYTHON" in issues[0].reason


# ---------------------------------------------------------------------------
# Plan → Apply split
# ---------------------------------------------------------------------------

def test_plan_returns_create_for_new_file(tmp_path: Path) -> None:
    """plan() returns action='create' for a new file."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    plans = pipeline.plan()
    assert len(plans) == 1
    assert plans[0].action == "create"


def test_plan_returns_skip_for_existing_file(tmp_path: Path) -> None:
    """plan() returns action='skip' for an existing file with SKIP policy."""
    target = tmp_path / "nginx" / "nginx.conf"
    target.parent.mkdir(parents=True)
    target.write_text("EXISTS")

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
        overwrite=OverwritePolicy.SKIP,
    )
    plans = _make_pipeline([artifact], tmp_path).plan()
    assert plans[0].action == "skip"


def test_plan_returns_overwrite_for_existing_file(tmp_path: Path) -> None:
    """plan() returns action='overwrite' for an existing file with OVERWRITE policy."""
    target = tmp_path / "nginx" / "nginx.conf"
    target.parent.mkdir(parents=True)
    target.write_text("EXISTS")

    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
        overwrite=OverwritePolicy.OVERWRITE,
    )
    plans = _make_pipeline([artifact], tmp_path).plan()
    assert plans[0].action == "overwrite"


def test_apply_executes_plan(tmp_path: Path) -> None:
    """apply(plan()) is equivalent to run(); the file is created."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    plans = pipeline.plan()
    results = pipeline.apply(plans)
    assert results[0].status == "created"
    assert (tmp_path / "nginx" / "nginx.conf").exists()


# ---------------------------------------------------------------------------
# --set parsing (unit test without starting the CLI)
# ---------------------------------------------------------------------------

def test_set_overrides_applied_to_answers(tmp_path: Path) -> None:
    """--set overrides the wizard answer in the template."""
    overridden_answers = {**NGINX_ANSWERS, "nginx_upstream": "custom-app:9999"}
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    results = _make_pipeline([artifact], tmp_path, answers=overridden_answers).run()
    assert results[0].status == "created"
    content = (tmp_path / "nginx" / "nginx.conf").read_text()
    assert "custom-app:9999" in content


# ---------------------------------------------------------------------------
# ArtifactContext — new fields (smart_env, depends_on, parent_service, service_def)
# ---------------------------------------------------------------------------

def test_artifact_context_new_fields_in_template_vars(tmp_path: Path) -> None:
    """as_template_vars() includes smart_env, depends_on, parent_service."""
    ctx = ArtifactContext(
        service_name="logstash",
        answers={},
        env_values={},
        project_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        preset=None,
        smart_env={"LOGSTASH_ES_HOST": "elasticsearch:9200"},
        depends_on=["elasticsearch"],
        parent_service="elasticsearch",
        service_def={"image": "logstash:8.13.0"},
    )
    tvars = ctx.as_template_vars()
    assert tvars["smart_env"] == {"LOGSTASH_ES_HOST": "elasticsearch:9200"}
    assert tvars["depends_on"] == ["elasticsearch"]
    assert tvars["parent_service"] == "elasticsearch"
    assert tvars["service_def"] == {"image": "logstash:8.13.0"}


def test_artifact_context_defaults_for_new_fields(tmp_path: Path) -> None:
    """New fields have safe defaults (empty collections / None)."""
    ctx = ArtifactContext(
        service_name="svc",
        answers={},
        env_values={},
        project_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
    )
    assert ctx.smart_env == {}
    assert ctx.depends_on == []
    assert ctx.parent_service is None
    assert ctx.service_def is None
    tvars = ctx.as_template_vars()
    assert tvars["smart_env"] == {}
    assert tvars["depends_on"] == []
    assert tvars["parent_service"] is None


# ---------------------------------------------------------------------------
# Logstash — templates
# ---------------------------------------------------------------------------

LOGSTASH_ANSWERS_STDOUT = {
    "logstash_pipeline": "beats-stdout",
    "logstash_pipeline_stdout": True,
    "logstash_pipeline_es": False,
}

LOGSTASH_ANSWERS_ES = {
    "logstash_pipeline": "beats-es",
    "logstash_pipeline_stdout": False,
    "logstash_pipeline_es": True,
    "logstash_es_host": "elasticsearch:9200",
}


def _make_logstash_context(base_dir: Path, answers: dict) -> ArtifactContext:
    return ArtifactContext(
        service_name="logstash",
        answers=answers,
        env_values={},
        project_root=base_dir,
        compose_file=base_dir / "docker-compose.yml",
        preset=None,
        smart_env=answers.get("smart_env", {}),
        depends_on=answers.get("depends_on", []),
        parent_service=answers.get("parent_service"),
        service_def=None,
    )


def test_logstash_beats_stdout_created(tmp_path: Path) -> None:
    """Logstash beats-stdout pipeline config is created when the condition is met."""
    artifact = ArtifactDef(
        relative_path="logstash/pipeline/logstash.conf",
        source_template="logstash/logstash-beats-stdout.conf.j2",
        condition="logstash_pipeline_stdout",
    )
    ctx = _make_logstash_context(tmp_path, LOGSTASH_ANSWERS_STDOUT)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert len(results) == 1
    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "beats" in content
    assert "5044" in content
    assert "stdout" in content
    assert "rubydebug" in content


def test_logstash_beats_stdout_skipped_when_es_mode(tmp_path: Path) -> None:
    """Logstash beats-stdout artifact is inactive when beats-es mode is selected."""
    artifact = ArtifactDef(
        relative_path="logstash/pipeline/logstash.conf",
        source_template="logstash/logstash-beats-stdout.conf.j2",
        condition="logstash_pipeline_stdout",
    )
    ctx = _make_logstash_context(tmp_path, LOGSTASH_ANSWERS_ES)
    pipeline = ArtifactPipeline([artifact], ctx)
    plans = pipeline.plan()
    # Condition is not met → artifact is not included in the plan.
    assert len(plans) == 0


def test_logstash_beats_es_created(tmp_path: Path) -> None:
    """Logstash beats-es pipeline config is created with the correct ES host."""
    artifact = ArtifactDef(
        relative_path="logstash/pipeline/logstash.conf",
        source_template="logstash/logstash-beats-es.conf.j2",
        condition="logstash_pipeline_es",
    )
    ctx = _make_logstash_context(tmp_path, LOGSTASH_ANSWERS_ES)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert len(results) == 1
    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "elasticsearch:9200" in content
    assert "elasticsearch" in content
    assert "beats" in content


def test_logstash_beats_es_uses_smart_env_host(tmp_path: Path) -> None:
    """ES host is taken from smart_env when logstash_es_host is not set explicitly."""
    answers = {
        "logstash_pipeline": "beats-es",
        "logstash_pipeline_stdout": False,
        "logstash_pipeline_es": True,
        "smart_env": {"LOGSTASH_ES_HOST": "my-es:9200"},
    }
    artifact = ArtifactDef(
        relative_path="logstash/pipeline/logstash.conf",
        source_template="logstash/logstash-beats-es.conf.j2",
        condition="logstash_pipeline_es",
    )
    ctx = _make_logstash_context(tmp_path, answers)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "my-es:9200" in content


def test_logstash_yml_always_created(tmp_path: Path) -> None:
    """logstash.yml is always created (no condition)."""
    artifact = ArtifactDef(
        relative_path="logstash/config/logstash.yml",
        source_template="logstash/logstash.yml.j2",
    )
    ctx = _make_logstash_context(tmp_path, LOGSTASH_ANSWERS_STDOUT)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "http.host" in content
    assert "9600" in content


def test_logstash_conditional_only_one_pipeline_active(tmp_path: Path) -> None:
    """Exactly one of two conditional artifacts is active."""
    artifacts = [
        ArtifactDef(
            relative_path="logstash/pipeline/logstash.conf",
            source_template="logstash/logstash-beats-stdout.conf.j2",
            condition="logstash_pipeline_stdout",
        ),
        ArtifactDef(
            relative_path="logstash/pipeline/logstash.conf",
            source_template="logstash/logstash-beats-es.conf.j2",
            condition="logstash_pipeline_es",
        ),
        ArtifactDef(
            relative_path="logstash/config/logstash.yml",
            source_template="logstash/logstash.yml.j2",
        ),
    ]
    # beats-es mode: only beats-es + logstash.yml are active.
    ctx = _make_logstash_context(tmp_path, LOGSTASH_ANSWERS_ES)
    pipeline = ArtifactPipeline(artifacts, ctx)
    plans = pipeline.plan()
    assert len(plans) == 2  # beats-es + logstash.yml
    active_templates = [p.artifact.source_template for p in plans]
    assert "logstash/logstash-beats-es.conf.j2" in active_templates
    assert "logstash/logstash.yml.j2" in active_templates
    assert "logstash/logstash-beats-stdout.conf.j2" not in active_templates


# ---------------------------------------------------------------------------
# Logstash smart_mapping
# ---------------------------------------------------------------------------

def test_logstash_smart_mapping_detects_elasticsearch() -> None:
    """_logstash_mapping sets ES_HOST and depends_on when elasticsearch exists."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("logstash", ["elasticsearch", "redis"], answers)
    assert result["depends_on"] == ["elasticsearch"]
    assert result["smart_env"]["LOGSTASH_ES_HOST"] == "elasticsearch:9200"
    assert result["logstash_pipeline"] == "beats-es"
    assert result["logstash_es_host"] == "elasticsearch:9200"


def test_logstash_smart_mapping_detects_opensearch() -> None:
    """_logstash_mapping also works with opensearch."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("logstash", ["opensearch"], answers)
    assert "opensearch" in result["depends_on"]
    assert "LOGSTASH_ES_HOST" in result["smart_env"]


def test_logstash_smart_mapping_noop_without_es() -> None:
    """_logstash_mapping does not change answers when ES/OpenSearch is missing."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("logstash", ["redis", "postgres"], answers)
    assert result.get("depends_on", []) == []
    assert result.get("smart_env", {}) == {}


def test_logstash_get_candidate_parents() -> None:
    """get_candidate_parents returns ES/OpenSearch services for logstash."""
    from rdt.smart_mapping import get_candidate_parents
    candidates = get_candidate_parents("logstash", ["elasticsearch", "redis", "opensearch"])
    assert "elasticsearch" in candidates
    assert "opensearch" in candidates
    assert "redis" not in candidates


# ---------------------------------------------------------------------------
# P2: ScaffoldPipeline — directory scaffolding
# ---------------------------------------------------------------------------

def test_scaffold_plan_create_for_new_dir(tmp_path: Path) -> None:
    """ScaffoldPipeline.plan() returns 'create' for a missing directory."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    dirs = [DirectoryDef(relative_path="logstash/pipeline")]
    sp = ScaffoldPipeline(dirs, tmp_path)
    plans = sp.plan()
    assert len(plans) == 1
    assert plans[0].action == "create"
    assert plans[0].target == tmp_path / "logstash/pipeline"


def test_scaffold_plan_skip_for_existing_dir(tmp_path: Path) -> None:
    """ScaffoldPipeline.plan() returns 'skip' for an existing directory."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    existing = tmp_path / "data"
    existing.mkdir()
    dirs = [DirectoryDef(relative_path="data")]
    sp = ScaffoldPipeline(dirs, tmp_path)
    plans = sp.plan()
    assert len(plans) == 1
    assert plans[0].action == "skip"


def test_scaffold_apply_creates_directories(tmp_path: Path) -> None:
    """ScaffoldPipeline.apply() creates directories and returns status='created'."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    dirs = [
        DirectoryDef(relative_path="logstash/pipeline"),
        DirectoryDef(relative_path="logstash/config"),
    ]
    sp = ScaffoldPipeline(dirs, tmp_path)
    results = sp.run()
    assert len(results) == 2
    assert all(r.status == "created" for r in results)
    assert (tmp_path / "logstash/pipeline").is_dir()
    assert (tmp_path / "logstash/config").is_dir()


def test_scaffold_apply_skip_existing(tmp_path: Path) -> None:
    """ScaffoldPipeline.apply() returns status='already_exists' for existing directories."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    existing = tmp_path / "nginx"
    existing.mkdir()
    dirs = [DirectoryDef(relative_path="nginx")]
    sp = ScaffoldPipeline(dirs, tmp_path)
    results = sp.run()
    assert len(results) == 1
    assert results[0].status == "already_exists"
    assert not results[0].has_error


def test_scaffold_has_errors_false(tmp_path: Path) -> None:
    """ScaffoldPipeline.has_errors() returns False for successful results."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline, ScaffoldResult
    results = [ScaffoldResult(path=tmp_path / "a", status="created")]
    assert ScaffoldPipeline.has_errors(results) is False


def test_scaffold_has_errors_true(tmp_path: Path) -> None:
    """ScaffoldPipeline.has_errors() returns True when there is an error."""
    from rdt.artifacts import ScaffoldPipeline, ScaffoldResult
    results = [ScaffoldResult(path=tmp_path / "a", status="error", error="permission denied")]
    assert ScaffoldPipeline.has_errors(results) is True


def test_scaffold_multiple_mixed(tmp_path: Path) -> None:
    """ScaffoldPipeline handles a mix of new and existing directories."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    existing = tmp_path / "existing"
    existing.mkdir()
    dirs = [
        DirectoryDef(relative_path="existing"),
        DirectoryDef(relative_path="new_dir"),
    ]
    sp = ScaffoldPipeline(dirs, tmp_path)
    results = sp.run()
    statuses = {r.path.name: r.status for r in results}
    assert statuses["existing"] == "already_exists"
    assert statuses["new_dir"] == "created"


# ---------------------------------------------------------------------------
# P2: BootstrapHint — bootstrap/artifact separation
# ---------------------------------------------------------------------------

def test_bootstrap_hint_fields() -> None:
    """BootstrapHint stores message and an optional command."""
    from rdt.artifacts import BootstrapHint
    hint = BootstrapHint(message="Run init script", command="docker exec -it svc init.sh")
    assert hint.message == "Run init script"
    assert hint.command == "docker exec -it svc init.sh"


def test_bootstrap_hint_without_command() -> None:
    """BootstrapHint works without a command."""
    from rdt.artifacts import BootstrapHint
    hint = BootstrapHint(message="Check logs manually")
    assert hint.message == "Check logs manually"
    assert hint.command is None


def test_service_preset_has_scaffolds_and_hints() -> None:
    """ServicePreset.scaffolds and bootstrap_hints are available and have correct types."""
    from rdt.presets.catalog import LOGSTASH
    from rdt.artifacts import DirectoryDef, BootstrapHint
    assert len(LOGSTASH.scaffolds) >= 2
    assert all(isinstance(d, DirectoryDef) for d in LOGSTASH.scaffolds)
    assert len(LOGSTASH.bootstrap_hints) >= 1
    assert all(isinstance(h, BootstrapHint) for h in LOGSTASH.bootstrap_hints)


def test_service_preset_scaffolds_paths() -> None:
    """LOGSTASH preset declares correct directory paths."""
    from rdt.presets.catalog import LOGSTASH
    paths = [d.relative_path for d in LOGSTASH.scaffolds]
    assert "logstash/pipeline" in paths
    assert "logstash/config" in paths


def test_logstash_scaffold_creates_dirs(tmp_path: Path) -> None:
    """ScaffoldPipeline + LOGSTASH.scaffolds creates logstash/pipeline and logstash/config."""
    from rdt.artifacts import ScaffoldPipeline
    from rdt.presets.catalog import LOGSTASH
    sp = ScaffoldPipeline(LOGSTASH.scaffolds, tmp_path)
    results = sp.run()
    assert all(r.status == "created" for r in results)
    assert (tmp_path / "logstash/pipeline").is_dir()
    assert (tmp_path / "logstash/config").is_dir()


def test_preset_without_scaffolds_has_empty_list() -> None:
    """ServicePreset without scaffolds has an empty list by default."""
    from rdt.presets.catalog import POSTGRES
    assert POSTGRES.scaffolds == []
    assert POSTGRES.bootstrap_hints == []


# ---------------------------------------------------------------------------
# Scaffold fatal errors
# ---------------------------------------------------------------------------

def test_scaffold_error_detected_by_has_errors(tmp_path: Path) -> None:
    """ScaffoldPipeline.has_errors() returns True when at least one directory was not created."""
    from rdt.artifacts import ScaffoldPipeline, ScaffoldResult
    # Create an error result directly.
    error_result = ScaffoldResult(path=tmp_path / "bad", status="error", error="permission denied")
    ok_result = ScaffoldResult(path=tmp_path / "ok", status="created")
    assert ScaffoldPipeline.has_errors([error_result, ok_result]) is True
    assert ScaffoldPipeline.has_errors([ok_result]) is False


def test_scaffold_apply_returns_error_on_permission_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ScaffoldPipeline.apply() returns status='error' when mkdir raises an exception."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    import pathlib

    # Patch Path.mkdir to raise PermissionError.
    original_mkdir = pathlib.Path.mkdir

    def mock_mkdir(self, *args, **kwargs):
        if self == tmp_path / "fail_dir":
            raise PermissionError("mocked permission error")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "mkdir", mock_mkdir)

    sp = ScaffoldPipeline([DirectoryDef(relative_path="fail_dir")], tmp_path)
    results = sp.run()
    assert len(results) == 1
    assert results[0].has_error is True
    assert "mocked permission error" in results[0].error


# ---------------------------------------------------------------------------
# Best-effort rollback
# ---------------------------------------------------------------------------

def test_rollback_restores_compose(tmp_path: Path) -> None:
    """_rollback restores the compose file from a snapshot."""
    from rdt.core import _rollback

    compose_file = tmp_path / "docker-compose.yml"
    original = "version: '3'\nservices: {}\n"
    compose_file.write_text(original + "# modified\n", encoding="utf-8")

    _rollback(
        compose_file=compose_file,
        compose_was_new=False,
        compose_snapshot=original,
        env_file=tmp_path / ".env",
        env_existed=False,
        env_snapshot=None,
        env_example=tmp_path / ".env.example",
        env_ex_existed=False,
        env_ex_snapshot=None,
        scaffold_results=[],
        artifact_results=[],
    )
    assert compose_file.read_text(encoding="utf-8") == original


def test_rollback_removes_new_compose(tmp_path: Path) -> None:
    """_rollback removes the compose file if it was created in the current run."""
    from rdt.core import _rollback

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("new content", encoding="utf-8")

    _rollback(
        compose_file=compose_file,
        compose_was_new=True,
        compose_snapshot=None,
        env_file=tmp_path / ".env",
        env_existed=False,
        env_snapshot=None,
        env_example=tmp_path / ".env.example",
        env_ex_existed=False,
        env_ex_snapshot=None,
        scaffold_results=[],
        artifact_results=[],
    )
    assert not compose_file.exists()


def test_rollback_removes_created_artifact(tmp_path: Path) -> None:
    """_rollback removes created artifacts (status='created')."""
    from rdt.core import _rollback
    from rdt.artifacts import ArtifactResult

    artifact_file = tmp_path / "nginx" / "nginx.conf"
    artifact_file.parent.mkdir(parents=True)
    artifact_file.write_text("conf content", encoding="utf-8")

    results = [ArtifactResult(path=artifact_file, status="created")]

    _rollback(
        compose_file=tmp_path / "docker-compose.yml",
        compose_was_new=False,
        compose_snapshot=None,
        env_file=tmp_path / ".env",
        env_existed=True,
        env_snapshot=None,
        env_example=tmp_path / ".env.example",
        env_ex_existed=True,
        env_ex_snapshot=None,
        scaffold_results=[],
        artifact_results=results,
    )
    assert not artifact_file.exists()


def test_rollback_removes_empty_scaffold_dir(tmp_path: Path) -> None:
    """_rollback removes empty scaffold directories (status='created')."""
    from rdt.core import _rollback
    from rdt.artifacts import ScaffoldResult

    scaffold_dir = tmp_path / "logstash" / "pipeline"
    scaffold_dir.mkdir(parents=True)

    results = [ScaffoldResult(path=scaffold_dir, status="created")]

    _rollback(
        compose_file=tmp_path / "docker-compose.yml",
        compose_was_new=False,
        compose_snapshot=None,
        env_file=tmp_path / ".env",
        env_existed=True,
        env_snapshot=None,
        env_example=tmp_path / ".env.example",
        env_ex_existed=True,
        env_ex_snapshot=None,
        scaffold_results=results,
        artifact_results=[],
    )
    assert not scaffold_dir.exists()


def test_rollback_does_not_remove_nonempty_scaffold_dir(tmp_path: Path) -> None:
    """_rollback does not remove non-empty scaffold directories."""
    from rdt.core import _rollback
    from rdt.artifacts import ScaffoldResult

    scaffold_dir = tmp_path / "logstash" / "pipeline"
    scaffold_dir.mkdir(parents=True)
    (scaffold_dir / "logstash.conf").write_text("pipeline {}", encoding="utf-8")

    results = [ScaffoldResult(path=scaffold_dir, status="created")]

    _rollback(
        compose_file=tmp_path / "docker-compose.yml",
        compose_was_new=False,
        compose_snapshot=None,
        env_file=tmp_path / ".env",
        env_existed=True,
        env_snapshot=None,
        env_example=tmp_path / ".env.example",
        env_ex_existed=True,
        env_ex_snapshot=None,
        scaffold_results=results,
        artifact_results=[],
    )
    # Directory should still exist because it's non-empty
    assert scaffold_dir.exists()


# ---------------------------------------------------------------------------
# Kibana preset integration
# ---------------------------------------------------------------------------

def test_kibana_preset_exists() -> None:
    """KIBANA preset exists in the catalog and has correct base fields."""
    from rdt.presets.catalog import ALL_PRESETS, KIBANA
    assert "kibana" in ALL_PRESETS
    assert ALL_PRESETS["kibana"] is KIBANA
    assert KIBANA.display_name == "Kibana"
    assert KIBANA.default_port == 5601
    assert KIBANA.container_port == 5601
    assert KIBANA.depends_on_category is not None


def test_kibana_preset_env_contains_required_keys() -> None:
    """KIBANA preset contains required environment variables."""
    from rdt.presets.catalog import KIBANA
    env_keys = set(KIBANA.default_env.keys())
    assert "ELASTICSEARCH_HOSTS" in env_keys
    assert "ELASTICSEARCH_USERNAME" in env_keys
    assert "ELASTICSEARCH_PASSWORD" in env_keys


def test_kibana_smart_mapping_detects_elasticsearch() -> None:
    """Kibana Smart Mapping correctly picks up the elasticsearch service."""
    from rdt.smart_mapping import apply_smart_mapping, get_candidate_parents
    existing = ["elasticsearch"]
    candidates = get_candidate_parents("kibana", existing)
    assert "elasticsearch" in candidates

    answers: dict = {}
    apply_smart_mapping("kibana", existing, answers)
    assert "elasticsearch" in answers.get("depends_on", [])
    assert "elasticsearch" in answers.get("smart_env", {}).get("ELASTICSEARCH_HOSTS", "")


def test_kibana_smart_mapping_detects_opensearch() -> None:
    """Kibana Smart Mapping correctly picks up the opensearch service."""
    from rdt.smart_mapping import apply_smart_mapping, get_candidate_parents
    existing = ["opensearch"]
    candidates = get_candidate_parents("kibana", existing)
    assert "opensearch" in candidates

    answers: dict = {}
    apply_smart_mapping("kibana", existing, answers)
    assert "opensearch" in answers.get("depends_on", [])


def test_kibana_smart_mapping_noop_without_es() -> None:
    """Kibana Smart Mapping does not add dependencies when ES/OpenSearch is missing."""
    from rdt.smart_mapping import apply_smart_mapping, get_candidate_parents
    existing = ["postgres", "redis"]
    candidates = get_candidate_parents("kibana", existing)
    assert candidates == []

    answers: dict = {}
    apply_smart_mapping("kibana", existing, answers)
    assert answers.get("depends_on", []) == []


def test_kibana_env_defaults_registered() -> None:
    """SERVICE_DEFAULTS contains values for Kibana credentials."""
    from rdt.env_manager import SERVICE_DEFAULTS
    assert "KIBANA_SYSTEM_PASSWORD" in SERVICE_DEFAULTS
    assert "KIBANA_ENCRYPTION_KEY" in SERVICE_DEFAULTS


def test_kibana_preset_has_bootstrap_hint() -> None:
    """KIBANA preset contains a bootstrap hint for configuring the kibana_system user."""
    from rdt.presets.catalog import KIBANA
    assert len(KIBANA.bootstrap_hints) >= 1
    hint = KIBANA.bootstrap_hints[0]
    assert "kibana_system" in hint.message.lower()


# ---------------------------------------------------------------------------
# Seq preset integration
# ---------------------------------------------------------------------------

def test_seq_preset_exists() -> None:
    """SEQ preset exists in the catalog and has correct base fields."""
    from rdt.presets.catalog import ALL_PRESETS, SEQ
    assert "seq" in ALL_PRESETS
    assert ALL_PRESETS["seq"] is SEQ
    assert "Seq" in SEQ.display_name
    assert SEQ.default_port == 5341


def test_seq_preset_env_contains_accept_eula() -> None:
    """SEQ preset contains ACCEPT_EULA in environment variables."""
    from rdt.presets.catalog import SEQ
    assert "ACCEPT_EULA" in SEQ.default_env
    assert SEQ.default_env["ACCEPT_EULA"] == "Y"


def test_seq_preset_no_artifacts() -> None:
    """SEQ preset does not require companion artifacts."""
    from rdt.presets.catalog import SEQ
    assert SEQ.artifacts == []
    assert SEQ.scaffolds == []


def test_seq_preset_has_volume() -> None:
    """SEQ preset declares a volume for persistent storage."""
    from rdt.presets.catalog import SEQ
    assert len(SEQ.volumes) >= 1


def test_seq_preset_has_bootstrap_hint() -> None:
    """SEQ preset contains a bootstrap hint."""
    from rdt.presets.catalog import SEQ
    assert len(SEQ.bootstrap_hints) >= 1


# ---------------------------------------------------------------------------
# Filebeat preset integration
# ---------------------------------------------------------------------------

def test_filebeat_preset_exists() -> None:
    """FILEBEAT preset exists in the catalog and has correct base fields."""
    from rdt.presets.catalog import ALL_PRESETS, FILEBEAT
    assert "filebeat" in ALL_PRESETS
    assert ALL_PRESETS["filebeat"] is FILEBEAT
    assert FILEBEAT.display_name == "Filebeat"
    assert FILEBEAT.default_port == 5066
    assert FILEBEAT.container_port == 5066


def test_filebeat_preset_has_volumes() -> None:
    """FILEBEAT preset declares volumes for config and data."""
    from rdt.presets.catalog import FILEBEAT
    assert len(FILEBEAT.volumes) >= 2
    volume_str = " ".join(FILEBEAT.volumes)
    assert "filebeat.yml" in volume_str
    assert "filebeat_data" in volume_str


def test_filebeat_preset_has_artifacts() -> None:
    """FILEBEAT preset contains 3 conditional artifacts (logstash / es / stdout)."""
    from rdt.presets.catalog import FILEBEAT
    assert len(FILEBEAT.artifacts) == 3
    conditions = {a.condition for a in FILEBEAT.artifacts}
    assert "filebeat_output_logstash" in conditions
    assert "filebeat_output_es" in conditions
    assert "filebeat_output_stdout" in conditions


def test_filebeat_preset_has_scaffold() -> None:
    """FILEBEAT preset declares the filebeat/ scaffold directory."""
    from rdt.presets.catalog import FILEBEAT
    from rdt.artifacts import DirectoryDef
    assert len(FILEBEAT.scaffolds) >= 1
    assert all(isinstance(d, DirectoryDef) for d in FILEBEAT.scaffolds)
    paths = [d.relative_path for d in FILEBEAT.scaffolds]
    assert "filebeat" in paths


def test_filebeat_preset_has_bootstrap_hints() -> None:
    """FILEBEAT preset contains bootstrap hints."""
    from rdt.presets.catalog import FILEBEAT
    assert len(FILEBEAT.bootstrap_hints) >= 1


# ---------------------------------------------------------------------------
# Filebeat — templates
# ---------------------------------------------------------------------------

FILEBEAT_ANSWERS_LOGSTASH = {
    "filebeat_output": "logstash",
    "filebeat_output_logstash": True,
    "filebeat_output_es": False,
    "filebeat_output_stdout": False,
    "filebeat_logstash_host": "logstash:5044",
    "filebeat_log_path": "/var/log/*.log",
    "filebeat_kibana_host": "",
}

FILEBEAT_ANSWERS_ES = {
    "filebeat_output": "elasticsearch",
    "filebeat_output_logstash": False,
    "filebeat_output_es": True,
    "filebeat_output_stdout": False,
    "filebeat_es_host": "elasticsearch:9200",
    "filebeat_log_path": "/var/log/*.log",
    "filebeat_kibana_host": "",
}

FILEBEAT_ANSWERS_STDOUT = {
    "filebeat_output": "stdout",
    "filebeat_output_logstash": False,
    "filebeat_output_es": False,
    "filebeat_output_stdout": True,
    "filebeat_log_path": "/var/log/*.log",
    "filebeat_kibana_host": "",
}


def _make_filebeat_context(base_dir: Path, answers: dict) -> ArtifactContext:
    return ArtifactContext(
        service_name="filebeat",
        answers=answers,
        env_values={},
        project_root=base_dir,
        compose_file=base_dir / "docker-compose.yml",
        preset=None,
        smart_env=answers.get("smart_env", {}),
        depends_on=answers.get("depends_on", []),
        parent_service=answers.get("parent_service"),
        service_def=None,
    )


def test_filebeat_logstash_template_created(tmp_path: Path) -> None:
    """filebeat-logstash.yml.j2 is created and contains the logstash host."""
    artifact = ArtifactDef(
        relative_path="filebeat/filebeat.yml",
        source_template="filebeat/filebeat-logstash.yml.j2",
        condition="filebeat_output_logstash",
        overwrite=OverwritePolicy.SKIP,
    )
    ctx = _make_filebeat_context(tmp_path, FILEBEAT_ANSWERS_LOGSTASH)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert len(results) == 1
    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "output.logstash" in content
    assert "logstash:5044" in content
    assert "filestream" in content


def test_filebeat_es_template_created(tmp_path: Path) -> None:
    """filebeat-es.yml.j2 is created and contains the elasticsearch host."""
    artifact = ArtifactDef(
        relative_path="filebeat/filebeat.yml",
        source_template="filebeat/filebeat-es.yml.j2",
        condition="filebeat_output_es",
        overwrite=OverwritePolicy.SKIP,
    )
    ctx = _make_filebeat_context(tmp_path, FILEBEAT_ANSWERS_ES)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert len(results) == 1
    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "output.elasticsearch" in content
    assert "elasticsearch:9200" in content


def test_filebeat_stdout_template_created(tmp_path: Path) -> None:
    """filebeat-stdout.yml.j2 is created for debug mode."""
    artifact = ArtifactDef(
        relative_path="filebeat/filebeat.yml",
        source_template="filebeat/filebeat-stdout.yml.j2",
        condition="filebeat_output_stdout",
        overwrite=OverwritePolicy.SKIP,
    )
    ctx = _make_filebeat_context(tmp_path, FILEBEAT_ANSWERS_STDOUT)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert len(results) == 1
    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "output.console" in content


def test_filebeat_logstash_template_skipped_in_es_mode(tmp_path: Path) -> None:
    """Logstash artifact is inactive when elasticsearch mode is selected."""
    artifact = ArtifactDef(
        relative_path="filebeat/filebeat.yml",
        source_template="filebeat/filebeat-logstash.yml.j2",
        condition="filebeat_output_logstash",
        overwrite=OverwritePolicy.SKIP,
    )
    ctx = _make_filebeat_context(tmp_path, FILEBEAT_ANSWERS_ES)
    pipeline = ArtifactPipeline([artifact], ctx)
    plans = pipeline.plan()
    assert len(plans) == 0  # condition is not met → inactive


def test_filebeat_conditional_only_one_active(tmp_path: Path) -> None:
    """Exactly one of three conditional artifacts is active in logstash mode."""
    from rdt.presets.catalog import FILEBEAT
    ctx = _make_filebeat_context(tmp_path, FILEBEAT_ANSWERS_LOGSTASH)
    pipeline = ArtifactPipeline(FILEBEAT.artifacts, ctx)
    plans = pipeline.plan()
    assert len(plans) == 1
    assert plans[0].artifact.condition == "filebeat_output_logstash"


def test_filebeat_kibana_host_rendered_in_logstash_template(tmp_path: Path) -> None:
    """setup.kibana section appears when filebeat_kibana_host is set."""
    answers = {**FILEBEAT_ANSWERS_LOGSTASH, "filebeat_kibana_host": "kibana:5601"}
    artifact = ArtifactDef(
        relative_path="filebeat/filebeat.yml",
        source_template="filebeat/filebeat-logstash.yml.j2",
        condition="filebeat_output_logstash",
    )
    ctx = _make_filebeat_context(tmp_path, answers)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    content = results[0].path.read_text()
    assert "setup.kibana" in content
    assert "kibana:5601" in content


def test_filebeat_kibana_section_absent_when_no_host(tmp_path: Path) -> None:
    """setup.kibana section is absent when filebeat_kibana_host is empty."""
    artifact = ArtifactDef(
        relative_path="filebeat/filebeat.yml",
        source_template="filebeat/filebeat-logstash.yml.j2",
        condition="filebeat_output_logstash",
    )
    ctx = _make_filebeat_context(tmp_path, FILEBEAT_ANSWERS_LOGSTASH)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    content = results[0].path.read_text()
    assert "setup.kibana" not in content


# ---------------------------------------------------------------------------
# Filebeat smart_mapping
# ---------------------------------------------------------------------------

def test_filebeat_smart_mapping_prefers_logstash() -> None:
    """Filebeat smart mapping chooses Logstash when both Logstash and ES exist."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("filebeat", ["elasticsearch", "logstash"], answers)
    assert result["filebeat_output"] == "logstash"
    assert result["filebeat_output_logstash"] is True
    assert result["filebeat_output_es"] is False
    assert "logstash" in result["depends_on"]
    assert result["smart_env"]["FILEBEAT_LOGSTASH_HOST"] == "logstash:5044"


def test_filebeat_smart_mapping_falls_back_to_es() -> None:
    """Filebeat smart mapping chooses ES when Logstash is absent."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("filebeat", ["elasticsearch", "redis"], answers)
    assert result["filebeat_output"] == "elasticsearch"
    assert result["filebeat_output_es"] is True
    assert "elasticsearch" in result["depends_on"]
    assert result["smart_env"]["FILEBEAT_ES_HOST"] == "elasticsearch:9200"


def test_filebeat_smart_mapping_falls_back_to_opensearch() -> None:
    """Filebeat smart mapping works with opensearch."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("filebeat", ["opensearch"], answers)
    assert result["filebeat_output"] == "elasticsearch"
    assert "opensearch" in result["depends_on"]


def test_filebeat_smart_mapping_stdout_when_no_target() -> None:
    """Filebeat smart mapping chooses stdout when neither Logstash nor ES exists."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("filebeat", ["redis", "postgres"], answers)
    assert result["filebeat_output"] == "stdout"
    assert result["filebeat_output_stdout"] is True


def test_filebeat_smart_mapping_detects_kibana() -> None:
    """Filebeat smart mapping adds Kibana host when Kibana is present."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("filebeat", ["logstash", "kibana"], answers)
    assert result["smart_env"]["FILEBEAT_KIBANA_HOST"] == "kibana:5601"
    assert "kibana" in result["depends_on"]


def test_filebeat_get_candidate_parents() -> None:
    """get_candidate_parents returns Logstash / ES / OpenSearch / Kibana for filebeat."""
    from rdt.smart_mapping import get_candidate_parents
    existing = ["logstash", "elasticsearch", "opensearch", "kibana", "redis"]
    candidates = get_candidate_parents("filebeat", existing)
    assert "logstash" in candidates
    assert "elasticsearch" in candidates
    assert "opensearch" in candidates
    assert "kibana" in candidates
    assert "redis" not in candidates


def test_filebeat_scaffold_creates_dir(tmp_path: Path) -> None:
    """ScaffoldPipeline + FILEBEAT.scaffolds creates filebeat/."""
    from rdt.artifacts import ScaffoldPipeline
    from rdt.presets.catalog import FILEBEAT
    sp = ScaffoldPipeline(FILEBEAT.scaffolds, tmp_path)
    results = sp.run()
    assert all(r.status == "created" for r in results)
    assert (tmp_path / "filebeat").is_dir()



# ---------------------------------------------------------------------------
# Traefik preset integration
# ---------------------------------------------------------------------------

def test_traefik_preset_exists() -> None:
    """TRAEFIK preset exists in the catalog and has correct base fields."""
    from rdt.presets.catalog import ALL_PRESETS, TRAEFIK
    assert "traefik" in ALL_PRESETS
    assert ALL_PRESETS["traefik"] is TRAEFIK
    assert "Traefik" in TRAEFIK.display_name
    assert TRAEFIK.default_port == 80
    assert TRAEFIK.container_port == 80
    assert TRAEFIK.strategy == "traefik"


def test_traefik_preset_has_artifact() -> None:
    """TRAEFIK preset contains exactly one companion artifact (traefik.yml)."""
    from rdt.presets.catalog import TRAEFIK
    assert len(TRAEFIK.artifacts) == 1
    art = TRAEFIK.artifacts[0]
    assert "traefik.yml" in art.relative_path
    assert "traefik.yml.j2" in art.source_template


def test_traefik_preset_has_scaffolds() -> None:
    """TRAEFIK preset declares traefik/ and traefik/dynamic/ scaffold directories."""
    from rdt.presets.catalog import TRAEFIK
    from rdt.artifacts import DirectoryDef
    assert len(TRAEFIK.scaffolds) >= 2
    assert all(isinstance(d, DirectoryDef) for d in TRAEFIK.scaffolds)
    paths = [d.relative_path for d in TRAEFIK.scaffolds]
    assert "traefik" in paths
    assert "traefik/dynamic" in paths


def test_traefik_preset_has_bootstrap_hints() -> None:
    """TRAEFIK preset contains at least three bootstrap hints."""
    from rdt.presets.catalog import TRAEFIK
    assert len(TRAEFIK.bootstrap_hints) >= 3


def test_traefik_preset_empty_env() -> None:
    """TRAEFIK preset has no required env variables (Traefik is configured via YAML)."""
    from rdt.presets.catalog import TRAEFIK
    assert TRAEFIK.default_env == {}


# ---------------------------------------------------------------------------
# TraefikStrategy — enrich
# ---------------------------------------------------------------------------

def _make_traefik_strategy(answers: dict):
    from rdt.strategies.traefik import TraefikStrategy
    from rdt.presets.catalog import TRAEFIK
    return TraefikStrategy(preset=TRAEFIK, answers=answers)


TRAEFIK_ANSWERS_BASIC = {
    "port": 80,
    "network_type": "bridge",
    "expose_ports": True,
    "traefik_dashboard": True,
    "dashboard_port": 8080,
    "traefik_dashboard_insecure": True,
    "traefik_https": False,
    "https_port": 443,
    "traefik_http_redirect": False,
    "traefik_config_dir": "./traefik",
}

TRAEFIK_ANSWERS_HTTPS = {
    **TRAEFIK_ANSWERS_BASIC,
    "traefik_https": True,
    "traefik_acme_email": "admin@example.com",
}


def test_traefik_strategy_ports_basic() -> None:
    """TraefikStrategy adds ports 80 and 8080 in basic mode."""
    strategy = _make_traefik_strategy(TRAEFIK_ANSWERS_BASIC)
    service: dict = {}
    strategy._enrich(service)
    assert "80:80" in service["ports"]
    assert "8080:8080" in service["ports"]
    # HTTPS is disabled, so port 443 must be absent.
    assert not any("443" in p for p in service["ports"])


def test_traefik_strategy_ports_https() -> None:
    """TraefikStrategy adds port 443 when HTTPS is enabled."""
    strategy = _make_traefik_strategy(TRAEFIK_ANSWERS_HTTPS)
    service: dict = {}
    strategy._enrich(service)
    assert any("443" in p for p in service["ports"])


def test_traefik_strategy_volumes_basic() -> None:
    """TraefikStrategy mounts docker.sock and traefik.yml without certs in basic mode."""
    strategy = _make_traefik_strategy(TRAEFIK_ANSWERS_BASIC)
    service: dict = {}
    strategy._enrich(service)
    volumes = service["volumes"]
    assert any("docker.sock" in v for v in volumes)
    assert any("traefik.yml" in v for v in volumes)
    assert not any("certs" in v for v in volumes)


def test_traefik_strategy_volumes_https() -> None:
    """TraefikStrategy adds a certs volume when HTTPS is enabled."""
    strategy = _make_traefik_strategy(TRAEFIK_ANSWERS_HTTPS)
    service: dict = {}
    strategy._enrich(service)
    volumes = service["volumes"]
    assert any("certs" in v for v in volumes)


def test_traefik_strategy_healthcheck() -> None:
    """TraefikStrategy sets healthcheck through the /ping endpoint."""
    strategy = _make_traefik_strategy(TRAEFIK_ANSWERS_BASIC)
    service: dict = {}
    strategy._enrich(service)
    hc = service["healthcheck"]
    assert "ping" in " ".join(hc["test"])
    assert hc["interval"] == "10s"
    assert hc["retries"] == 3


def test_traefik_strategy_no_ports_when_host_network() -> None:
    """TraefikStrategy does not add ports when network_type=host."""
    answers = {**TRAEFIK_ANSWERS_BASIC, "network_type": "host"}
    strategy = _make_traefik_strategy(answers)
    service: dict = {}
    strategy._enrich(service)
    assert "ports" not in service


# ---------------------------------------------------------------------------
# Traefik — traefik.yml.j2 template
# ---------------------------------------------------------------------------

def _make_traefik_artifact_context(base_dir: Path, answers: dict) -> ArtifactContext:
    return ArtifactContext(
        service_name="traefik",
        answers=answers,
        env_values={},
        project_root=base_dir,
        compose_file=base_dir / "docker-compose.yml",
        preset=None,
        smart_env={},
        depends_on=[],
        parent_service=None,
        service_def=None,
    )


def test_traefik_yml_template_created_basic(tmp_path: Path) -> None:
    """traefik.yml.j2 renders correctly in basic mode (without HTTPS)."""
    artifact = ArtifactDef(
        relative_path="traefik/traefik.yml",
        source_template="traefik/traefik.yml.j2",
        overwrite=OverwritePolicy.SKIP,
    )
    ctx = _make_traefik_artifact_context(tmp_path, {**TRAEFIK_ANSWERS_BASIC})
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    assert len(results) == 1
    assert results[0].status == "created"
    content = results[0].path.read_text()
    assert "entryPoints" in content
    assert "web:" in content
    assert "ping" in content
    assert "dashboard: true" in content


def test_traefik_yml_template_no_https_block_when_disabled(tmp_path: Path) -> None:
    """traefik.yml.j2 does not contain certificatesResolvers when HTTPS is disabled."""
    artifact = ArtifactDef(
        relative_path="traefik/traefik.yml",
        source_template="traefik/traefik.yml.j2",
        overwrite=OverwritePolicy.SKIP,
    )
    ctx = _make_traefik_artifact_context(tmp_path, {**TRAEFIK_ANSWERS_BASIC, "traefik_https": False})
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    content = results[0].path.read_text()
    assert "certificatesResolvers" not in content
    assert "websecure" not in content


def test_traefik_yml_template_has_https_block_when_enabled(tmp_path: Path) -> None:
    """traefik.yml.j2 contains websecure and certificatesResolvers with HTTPS."""
    artifact = ArtifactDef(
        relative_path="traefik/traefik.yml",
        source_template="traefik/traefik.yml.j2",
        overwrite=OverwritePolicy.SKIP,
    )
    answers = {**TRAEFIK_ANSWERS_HTTPS, "traefik_acme_email": "test@example.com"}
    ctx = _make_traefik_artifact_context(tmp_path, answers)
    pipeline = ArtifactPipeline([artifact], ctx)
    results = pipeline.run()

    content = results[0].path.read_text()
    assert "websecure" in content
    assert "certificatesResolvers" in content
    assert "test@example.com" in content


# ---------------------------------------------------------------------------
# Traefik — scaffold
# ---------------------------------------------------------------------------

def test_traefik_scaffold_creates_dirs(tmp_path: Path) -> None:
    """ScaffoldPipeline + TRAEFIK.scaffolds creates traefik/ and traefik/dynamic/."""
    from rdt.artifacts import ScaffoldPipeline
    from rdt.presets.catalog import TRAEFIK
    sp = ScaffoldPipeline(TRAEFIK.scaffolds, tmp_path)
    results = sp.run()
    assert all(r.status == "created" for r in results)
    assert (tmp_path / "traefik").is_dir()
    assert (tmp_path / "traefik" / "dynamic").is_dir()


# ---------------------------------------------------------------------------
# YAML manager — healthcheck inline flow style
# ---------------------------------------------------------------------------

def test_dict_to_commented_healthcheck_test_flow_style() -> None:
    """healthcheck.test is serialized in inline flow style."""
    from rdt.yaml_manager import _dict_to_commented
    from ruamel.yaml.comments import CommentedSeq

    d = {
        "healthcheck": {
            "test": ["CMD-SHELL", "pg_isready || exit 1"],
            "interval": "10s",
        },
        "ports": ["5432:5432"],
    }
    cm = _dict_to_commented(d)

    test_seq = cm["healthcheck"]["test"]
    assert isinstance(test_seq, CommentedSeq)
    assert test_seq.fa.flow_style() is True

    ports_seq = cm["ports"]
    assert isinstance(ports_seq, CommentedSeq)
    assert ports_seq.fa.flow_style() is not True


def test_save_compose_healthcheck_test_inline(tmp_path: Path) -> None:
    """save_compose writes healthcheck.test as an inline array."""
    from rdt.yaml_manager import save_compose, make_base_compose, inject_service

    data = make_base_compose()
    service_def = {
        "image": "postgres:16",
        "healthcheck": {
            "test": ["CMD-SHELL", "pg_isready -U postgres || exit 1"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 3,
        },
        "ports": ["5432:5432"],
        "volumes": ["pg_data:/var/lib/postgresql/data"],
        "networks": ["rambo-net"],
    }
    inject_service(data, "db", service_def)

    compose_file = tmp_path / "docker-compose.yml"
    save_compose(compose_file, data)
    content = compose_file.read_text(encoding="utf-8")

    assert "test: [CMD-SHELL, pg_isready -U postgres || exit 1]" in content
    assert "ports:\n    - " in content  # block-style under services.db
    assert "volumes:\n    - pg_data:/var/lib/postgresql/data" in content
    assert "networks:\n    - rambo-net" in content


def test_save_compose_normalizes_existing_healthcheck_test(tmp_path: Path) -> None:
    """save_compose normalizes already loaded block-style healthcheck.test."""
    from rdt.yaml_manager import save_compose, load_compose

    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(
        """
services:
  db:
    image: postgres:16
    healthcheck:
      test:
      - CMD-SHELL
      - pg_isready -U postgres || exit 1
      interval: 10s
""".lstrip(),
        encoding="utf-8",
    )

    data = load_compose(compose_file)
    save_compose(compose_file, data)
    content = compose_file.read_text(encoding="utf-8")

    assert "test: [CMD-SHELL, pg_isready -U postgres || exit 1]" in content
    assert "test:\n" not in content


def test_save_compose_traefik_healthcheck_inline(tmp_path: Path) -> None:
    """TraefikStrategy + save_compose produces inline healthcheck.test."""
    from rdt.strategies.traefik import TraefikStrategy
    from rdt.presets.catalog import TRAEFIK
    from rdt.yaml_manager import save_compose, make_base_compose, inject_service

    strategy = TraefikStrategy(
        TRAEFIK,
        {
            "port": 80,
            "network_name": "rambo-net",
            "traefik_config_dir": "./traefik",
        },
    )
    svc = strategy.build()
    data = make_base_compose()
    inject_service(data, "traefik", svc)

    compose_file = tmp_path / "docker-compose.yml"
    save_compose(compose_file, data)
    content = compose_file.read_text(encoding="utf-8")

    assert "test: [CMD-SHELL, wget -qO- http://localhost:8080/ping || exit 1]" in content
