"""
Smoke / functional tests для ArtifactPipeline (core-hardening M1–M3).

Покрывают:
- успешную генерацию nginx-proxy, nginx-static, nginx-spa (TEMPLATE)
- ArtifactSourceType.STATIC и ArtifactSourceType.PYTHON
- ArtifactContext.as_template_vars()
- политику SKIP (существующий файл не перезаписывается)
- политику OVERWRITE (существующий файл перезаписывается)
- политику ERROR_IF_EXISTS (ошибка если файл уже существует)
- preflight: обнаружение отсутствующего шаблона
- preflight: обнаружение конфликта ERROR_IF_EXISTS
- preflight: обнаружение STATIC без static_content
- preflight: обнаружение PYTHON без renderer
- preflight: успешный проход без проблем
- has_errors() helper
- корректную работу с нестандартным project_root (аналог --file)
- падение при ошибке шаблона (несуществующий шаблон)
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
# Хелперы
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
# Успешная генерация
# ---------------------------------------------------------------------------

def test_nginx_proxy_created(tmp_path: Path) -> None:
    """Pipeline создаёт nginx/nginx.conf для nginx-proxy."""
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
    """Pipeline создаёт nginx/nginx.conf для nginx-static."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-static.conf.j2",
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "created"
    assert results[0].path.exists()


def test_nginx_spa_created(tmp_path: Path) -> None:
    """Pipeline создаёт nginx/nginx.conf для nginx-spa."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-spa.conf.j2",
    )
    results = _make_pipeline([artifact], tmp_path).run()
    assert results[0].status == "created"
    assert results[0].path.exists()


# ---------------------------------------------------------------------------
# Политики перезаписи
# ---------------------------------------------------------------------------

def test_skip_existing_file(tmp_path: Path) -> None:
    """SKIP: существующий файл не перезаписывается."""
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
    """OVERWRITE: существующий файл перезаписывается."""
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
    """ERROR_IF_EXISTS: возвращает ошибку если файл уже существует."""
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
    # Файл не должен быть изменён
    assert target.read_text() == "ORIGINAL"




# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def test_preflight_ok(tmp_path: Path) -> None:
    """Preflight не возвращает проблем для валидного артефакта."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert issues == []


def test_preflight_catches_missing_template(tmp_path: Path) -> None:
    """Preflight обнаруживает отсутствующий шаблон."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/DOES_NOT_EXIST.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert len(issues) == 1
    assert "DOES_NOT_EXIST" in issues[0].reason


def test_preflight_catches_error_if_exists(tmp_path: Path) -> None:
    """Preflight обнаруживает ERROR_IF_EXISTS конфликт до записи."""
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
    """Preflight пропускает артефакты с невыполненным условием."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/DOES_NOT_EXIST.conf.j2",
        condition="generate_nginx",  # ключ отсутствует в answers
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    issues = pipeline.preflight()
    assert issues == []  # условие не выполнено → артефакт неактивен, проблем нет


# ---------------------------------------------------------------------------
# Падение при ошибке шаблона
# ---------------------------------------------------------------------------

def test_missing_template_returns_error(tmp_path: Path) -> None:
    """Несуществующий шаблон → статус 'error', не исключение."""
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
    """has_errors возвращает True если есть хотя бы одна ошибка."""
    results = [
        ArtifactResult(path=Path("a"), status="created"),
        ArtifactResult(path=Path("b"), status="error", error="oops"),
    ]
    assert ArtifactPipeline.has_errors(results) is True


def test_has_errors_false() -> None:
    """has_errors возвращает False если нет ошибок."""
    results = [
        ArtifactResult(path=Path("a"), status="created"),
        ArtifactResult(path=Path("b"), status="skipped"),
    ]
    assert ArtifactPipeline.has_errors(results) is False


# ---------------------------------------------------------------------------
# Работа с нестандартным base_dir (аналог --file)
# ---------------------------------------------------------------------------

def test_custom_base_dir(tmp_path: Path) -> None:
    """Артефакты генерируются относительно переданного base_dir."""
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
    # Файл не должен появиться в tmp_path напрямую
    assert not (tmp_path / "nginx" / "nginx.conf").exists()


# ---------------------------------------------------------------------------
# Тест _resolve_project_root из cli
# ---------------------------------------------------------------------------

def test_resolve_project_root_default() -> None:
    """Для docker-compose.yml в cwd root == cwd."""
    from rdt.cli import _resolve_project_root
    result = _resolve_project_root(Path("docker-compose.yml"))
    assert result == Path.cwd().resolve()


def test_resolve_project_root_subdir(tmp_path: Path) -> None:
    """Для файла в поддиректории root == поддиректория."""
    from rdt.cli import _resolve_project_root
    compose = tmp_path / "infra" / "docker-compose.yml"
    result = _resolve_project_root(compose)
    assert result == (tmp_path / "infra").resolve()



# ---------------------------------------------------------------------------
# ArtifactContext
# ---------------------------------------------------------------------------

def test_artifact_context_as_template_vars(tmp_path: Path) -> None:
    """as_template_vars() включает answers + служебные поля."""
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
    """as_template_vars() включает preset_name и preset_display_name если preset задан."""
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
    """STATIC: записывает static_content в целевой файл."""
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
    """Preflight обнаруживает STATIC без static_content."""
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
    """PYTHON: вызывает renderer(context) и записывает результат."""
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
    """Preflight обнаруживает PYTHON без renderer."""
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
    """plan() возвращает action='create' для нового файла."""
    artifact = ArtifactDef(
        relative_path="nginx/nginx.conf",
        source_template="nginx/nginx-proxy.conf.j2",
    )
    pipeline = _make_pipeline([artifact], tmp_path)
    plans = pipeline.plan()
    assert len(plans) == 1
    assert plans[0].action == "create"


def test_plan_returns_skip_for_existing_file(tmp_path: Path) -> None:
    """plan() возвращает action='skip' для существующего файла с политикой SKIP."""
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
    """plan() возвращает action='overwrite' для существующего файла с политикой OVERWRITE."""
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
    """apply(plan()) эквивалентен run() — файл создаётся."""
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
# --set parsing (unit test — без запуска CLI)
# ---------------------------------------------------------------------------

def test_set_overrides_applied_to_answers(tmp_path: Path) -> None:
    """--set переопределяет ответ мастера в шаблоне."""
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
# ArtifactContext — новые поля (smart_env, depends_on, parent_service, service_def)
# ---------------------------------------------------------------------------

def test_artifact_context_new_fields_in_template_vars(tmp_path: Path) -> None:
    """as_template_vars() включает smart_env, depends_on, parent_service."""
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
    """Новые поля имеют безопасные defaults (пустые коллекции / None)."""
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
# Logstash — шаблоны
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
    """Logstash beats-stdout pipeline config создаётся когда условие выполнено."""
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
    """Logstash beats-stdout артефакт неактивен когда выбран режим beats-es."""
    artifact = ArtifactDef(
        relative_path="logstash/pipeline/logstash.conf",
        source_template="logstash/logstash-beats-stdout.conf.j2",
        condition="logstash_pipeline_stdout",
    )
    ctx = _make_logstash_context(tmp_path, LOGSTASH_ANSWERS_ES)
    pipeline = ArtifactPipeline([artifact], ctx)
    plans = pipeline.plan()
    # Условие не выполнено → артефакт не включён в план
    assert len(plans) == 0


def test_logstash_beats_es_created(tmp_path: Path) -> None:
    """Logstash beats-es pipeline config создаётся с правильным ES host."""
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
    """ES host берётся из smart_env если logstash_es_host не задан явно."""
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
    """logstash.yml создаётся всегда (нет условия)."""
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
    """Из двух conditional артефактов активен ровно один."""
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
    # Режим beats-es: активны только beats-es + logstash.yml
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
    """_logstash_mapping устанавливает ES_HOST и depends_on при наличии elasticsearch."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("logstash", ["elasticsearch", "redis"], answers)
    assert result["depends_on"] == ["elasticsearch"]
    assert result["smart_env"]["LOGSTASH_ES_HOST"] == "elasticsearch:9200"
    assert result["logstash_pipeline"] == "beats-es"
    assert result["logstash_es_host"] == "elasticsearch:9200"


def test_logstash_smart_mapping_detects_opensearch() -> None:
    """_logstash_mapping работает и с opensearch."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("logstash", ["opensearch"], answers)
    assert "opensearch" in result["depends_on"]
    assert "LOGSTASH_ES_HOST" in result["smart_env"]


def test_logstash_smart_mapping_noop_without_es() -> None:
    """_logstash_mapping не изменяет answers если ES/OpenSearch не найден."""
    from rdt.smart_mapping import apply_smart_mapping
    answers: dict = {}
    result = apply_smart_mapping("logstash", ["redis", "postgres"], answers)
    assert result.get("depends_on", []) == []
    assert result.get("smart_env", {}) == {}


def test_logstash_get_candidate_parents() -> None:
    """get_candidate_parents возвращает ES/OpenSearch сервисы для logstash."""
    from rdt.smart_mapping import get_candidate_parents
    candidates = get_candidate_parents("logstash", ["elasticsearch", "redis", "opensearch"])
    assert "elasticsearch" in candidates
    assert "opensearch" in candidates
    assert "redis" not in candidates


# ---------------------------------------------------------------------------
# P2: ScaffoldPipeline — directory scaffolding
# ---------------------------------------------------------------------------

def test_scaffold_plan_create_for_new_dir(tmp_path: Path) -> None:
    """ScaffoldPipeline.plan() возвращает 'create' для несуществующей директории."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    dirs = [DirectoryDef(relative_path="logstash/pipeline")]
    sp = ScaffoldPipeline(dirs, tmp_path)
    plans = sp.plan()
    assert len(plans) == 1
    assert plans[0].action == "create"
    assert plans[0].target == tmp_path / "logstash/pipeline"


def test_scaffold_plan_skip_for_existing_dir(tmp_path: Path) -> None:
    """ScaffoldPipeline.plan() возвращает 'skip' для уже существующей директории."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline
    existing = tmp_path / "data"
    existing.mkdir()
    dirs = [DirectoryDef(relative_path="data")]
    sp = ScaffoldPipeline(dirs, tmp_path)
    plans = sp.plan()
    assert len(plans) == 1
    assert plans[0].action == "skip"


def test_scaffold_apply_creates_directories(tmp_path: Path) -> None:
    """ScaffoldPipeline.apply() создаёт директории и возвращает status='created'."""
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
    """ScaffoldPipeline.apply() возвращает status='already_exists' для существующих директорий."""
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
    """ScaffoldPipeline.has_errors() возвращает False при успешных результатах."""
    from rdt.artifacts import DirectoryDef, ScaffoldPipeline, ScaffoldResult
    results = [ScaffoldResult(path=tmp_path / "a", status="created")]
    assert ScaffoldPipeline.has_errors(results) is False


def test_scaffold_has_errors_true(tmp_path: Path) -> None:
    """ScaffoldPipeline.has_errors() возвращает True если есть ошибка."""
    from rdt.artifacts import ScaffoldPipeline, ScaffoldResult
    results = [ScaffoldResult(path=tmp_path / "a", status="error", error="permission denied")]
    assert ScaffoldPipeline.has_errors(results) is True


def test_scaffold_multiple_mixed(tmp_path: Path) -> None:
    """ScaffoldPipeline обрабатывает mix новых и существующих директорий."""
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
# P2: BootstrapHint — разграничение bootstrap/artifact
# ---------------------------------------------------------------------------

def test_bootstrap_hint_fields() -> None:
    """BootstrapHint хранит message и опциональный command."""
    from rdt.artifacts import BootstrapHint
    hint = BootstrapHint(message="Run init script", command="docker exec -it svc init.sh")
    assert hint.message == "Run init script"
    assert hint.command == "docker exec -it svc init.sh"


def test_bootstrap_hint_without_command() -> None:
    """BootstrapHint работает без команды."""
    from rdt.artifacts import BootstrapHint
    hint = BootstrapHint(message="Check logs manually")
    assert hint.message == "Check logs manually"
    assert hint.command is None


def test_service_preset_has_scaffolds_and_hints() -> None:
    """ServicePreset.scaffolds и bootstrap_hints доступны и имеют правильные типы."""
    from rdt.presets.catalog import LOGSTASH
    from rdt.artifacts import DirectoryDef, BootstrapHint
    assert len(LOGSTASH.scaffolds) >= 2
    assert all(isinstance(d, DirectoryDef) for d in LOGSTASH.scaffolds)
    assert len(LOGSTASH.bootstrap_hints) >= 1
    assert all(isinstance(h, BootstrapHint) for h in LOGSTASH.bootstrap_hints)


def test_service_preset_scaffolds_paths() -> None:
    """LOGSTASH пресет декларирует корректные пути директорий."""
    from rdt.presets.catalog import LOGSTASH
    paths = [d.relative_path for d in LOGSTASH.scaffolds]
    assert "logstash/pipeline" in paths
    assert "logstash/config" in paths


def test_logstash_scaffold_creates_dirs(tmp_path: Path) -> None:
    """ScaffoldPipeline + LOGSTASH.scaffolds создаёт logstash/pipeline и logstash/config."""
    from rdt.artifacts import ScaffoldPipeline
    from rdt.presets.catalog import LOGSTASH
    sp = ScaffoldPipeline(LOGSTASH.scaffolds, tmp_path)
    results = sp.run()
    assert all(r.status == "created" for r in results)
    assert (tmp_path / "logstash/pipeline").is_dir()
    assert (tmp_path / "logstash/config").is_dir()


def test_preset_without_scaffolds_has_empty_list() -> None:
    """ServicePreset без scaffolds имеет пустой список по умолчанию."""
    from rdt.presets.catalog import POSTGRES
    assert POSTGRES.scaffolds == []
    assert POSTGRES.bootstrap_hints == []
