"""
Подсистема companion-артефактов RDT.

Позволяет сервисам генерировать дополнительные файлы конфигурации
(nginx.conf, logstash.conf, prometheus.yml и т.д.) вместе с compose-блоком.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from rdt.i18n import t


# ---------------------------------------------------------------------------
# Политика перезаписи
# ---------------------------------------------------------------------------

class OverwritePolicy(str, Enum):
    SKIP = "skip"                       # не перезаписывать если файл уже существует
    OVERWRITE = "overwrite"             # всегда перезаписывать
    ERROR_IF_EXISTS = "error_if_exists" # вернуть ошибку если файл уже существует


# ---------------------------------------------------------------------------
# Тип источника артефакта
# ---------------------------------------------------------------------------

class ArtifactSourceType(str, Enum):
    TEMPLATE = "template"  # Jinja2-шаблон из templates/artifacts/
    STATIC = "static"      # Статический текст, встроенный в ArtifactDef
    PYTHON = "python"      # Python-рендерер: (context: ArtifactContext) -> str


# ---------------------------------------------------------------------------
# Богатый контекст генерации артефактов
# ---------------------------------------------------------------------------

@dataclass
class ArtifactContext:
    """
    Полный контекст для генерации companion-артефактов сервиса.

    Передаётся в ArtifactPipeline вместо сырого dict answers.
    Доступен в Jinja2-шаблонах и Python-рендерерах.
    """

    service_name: str
    """Имя сервиса (ключ в docker-compose, например 'nginx-proxy')."""

    answers: dict[str, Any]
    """Ответы мастера или скрипт-режима."""

    env_values: dict[str, str]
    """Значения переменных окружения, записываемых в .env."""

    project_root: Path
    """Корень проекта — от него строятся все пути артефактов."""

    compose_file: Path
    """Абсолютный путь к docker-compose.yml."""

    preset: Any = None
    """ServicePreset (Any — чтобы избежать circular import из presets/catalog.py)."""

    def as_template_vars(self) -> dict[str, Any]:
        """
        Возвращает все переменные для Jinja2-рендера.
        Включает answers + служебные поля контекста.
        """
        base: dict[str, Any] = {**self.answers}
        base["service_name"] = self.service_name
        base["project_root"] = str(self.project_root)
        base["compose_file"] = str(self.compose_file)
        base["env_values"] = self.env_values
        if self.preset is not None:
            base["preset_name"] = self.preset.name
            base["preset_display_name"] = self.preset.display_name
        return base


# ---------------------------------------------------------------------------
# Модель описания артефакта
# ---------------------------------------------------------------------------

@dataclass
class ArtifactDef:
    """Описание companion-файла, генерируемого вместе с сервисом."""

    relative_path: str
    """Куда записать файл относительно project_root (например: 'nginx/nginx.conf')."""

    source_template: str | None = None
    """Путь к Jinja2-шаблону относительно rdt/templates/artifacts/. Используется при source_type=TEMPLATE."""

    source_type: ArtifactSourceType = ArtifactSourceType.TEMPLATE
    """Тип источника содержимого файла."""

    static_content: str | None = None
    """Готовый текст файла. Используется при source_type=STATIC."""

    renderer: Callable[[ArtifactContext], str] | None = None
    """Python-рендерер. Используется при source_type=PYTHON."""

    overwrite: OverwritePolicy = OverwritePolicy.SKIP
    """Политика поведения при существующем файле."""

    condition: str | None = None
    """Ключ в answers — генерировать только если answers[condition] truthy."""

    extra_vars: dict[str, Any] = field(default_factory=dict)
    """Дополнительные переменные для шаблона (поверх context.as_template_vars())."""


# ---------------------------------------------------------------------------
# Результат preflight-проверки
# ---------------------------------------------------------------------------

@dataclass
class PreflightIssue:
    """Одна проблема, найденная при preflight-проверке."""
    artifact_path: str
    reason: str


# ---------------------------------------------------------------------------
# Результат генерации
# ---------------------------------------------------------------------------

@dataclass
class ArtifactResult:
    """Результат генерации одного артефакта."""

    path: Path
    status: str  # "created" | "skipped" | "overwritten" | "error"
    error: str | None = None

    @property
    def has_error(self) -> bool:
        return self.status == "error"


# ---------------------------------------------------------------------------
# Запланированное действие (plan → apply)
# ---------------------------------------------------------------------------

@dataclass
class ArtifactPlan:
    """Запланированное действие для одного артефакта (до фактической записи)."""

    artifact: ArtifactDef
    target: Path
    action: Literal["create", "overwrite", "skip", "error"]
    error: str | None = None


# ---------------------------------------------------------------------------
# Pipeline генерации артефактов
# ---------------------------------------------------------------------------

class ArtifactPipeline:
    """
    Pipeline генерации companion-файлов сервиса.

    Архитектура plan → apply:
    1. preflight() — проверить шаблоны, пути и политики до записи
    2. plan()      — построить список запланированных действий без записи
    3. apply()     — выполнить план: рендер + запись файлов
    4. run()       — ярлык: plan() → apply()
    """

    #: Директория с шаблонами артефактов (внутри пакета rdt)
    TEMPLATES_DIR: Path = Path(__file__).parent / "templates" / "artifacts"

    def __init__(
        self,
        artifacts: list[ArtifactDef],
        context: ArtifactContext,
    ) -> None:
        self.artifacts = artifacts
        self.context = context

    @property
    def base_dir(self) -> Path:
        """Корень проекта из контекста."""
        return self.context.project_root

    # ---------------------------------------------------------------------------
    # Preflight
    # ---------------------------------------------------------------------------

    def preflight(self) -> list[PreflightIssue]:
        """
        Проверить готовность всех активных артефактов к генерации.
        Возвращает список найденных проблем (пустой — значит всё ок).
        """
        issues: list[PreflightIssue] = []
        for artifact in self.artifacts:
            # Пропустить если условие не выполнено
            if artifact.condition and not self.context.answers.get(artifact.condition):
                continue

            target = self.base_dir / artifact.relative_path

            # 1. Проверить источник содержимого
            if artifact.source_type == ArtifactSourceType.TEMPLATE:
                if artifact.source_template is None:
                    issues.append(PreflightIssue(
                        artifact_path=artifact.relative_path,
                        reason=t("artifacts.preflight.template_missing", template="<None>"),
                    ))
                else:
                    template_path = self.TEMPLATES_DIR / artifact.source_template
                    if not template_path.exists():
                        issues.append(PreflightIssue(
                            artifact_path=artifact.relative_path,
                            reason=t("artifacts.preflight.template_missing", template=artifact.source_template),
                        ))
            elif artifact.source_type == ArtifactSourceType.STATIC and artifact.static_content is None:
                issues.append(PreflightIssue(
                    artifact_path=artifact.relative_path,
                    reason=t("artifacts.preflight.static_content_missing"),
                ))
            elif artifact.source_type == ArtifactSourceType.PYTHON and artifact.renderer is None:
                issues.append(PreflightIssue(
                    artifact_path=artifact.relative_path,
                    reason=t("artifacts.preflight.renderer_missing"),
                ))

            # 2. Проверить политику при существующем файле
            if target.exists() and artifact.overwrite == OverwritePolicy.ERROR_IF_EXISTS:
                issues.append(PreflightIssue(
                    artifact_path=artifact.relative_path,
                    reason=t("artifacts.preflight.file_exists", path=str(target)),
                ))

            # 3. Проверить доступность родительской директории (если уже существует)
            parent = target.parent
            if parent.exists() and not parent.is_dir():
                issues.append(PreflightIssue(
                    artifact_path=artifact.relative_path,
                    reason=t("artifacts.preflight.parent_not_dir", path=str(parent)),
                ))

        return issues

    # ---------------------------------------------------------------------------
    # Plan
    # ---------------------------------------------------------------------------

    def plan(self) -> list[ArtifactPlan]:
        """
        Определить что будет сделано с каждым активным артефактом без фактической записи.
        Возвращает список ArtifactPlan с action: create | overwrite | skip | error.
        """
        plans: list[ArtifactPlan] = []
        for artifact in self.artifacts:
            if artifact.condition and not self.context.answers.get(artifact.condition):
                continue

            target = self.base_dir / artifact.relative_path
            already_exists = target.exists()

            if already_exists:
                if artifact.overwrite == OverwritePolicy.SKIP:
                    plans.append(ArtifactPlan(artifact=artifact, target=target, action="skip"))
                elif artifact.overwrite == OverwritePolicy.ERROR_IF_EXISTS:
                    plans.append(ArtifactPlan(
                        artifact=artifact,
                        target=target,
                        action="error",
                        error=t("artifacts.preflight.file_exists", path=str(target)),
                    ))
                else:  # OVERWRITE
                    plans.append(ArtifactPlan(artifact=artifact, target=target, action="overwrite"))
            else:
                plans.append(ArtifactPlan(artifact=artifact, target=target, action="create"))

        return plans

    # ---------------------------------------------------------------------------
    # Apply
    # ---------------------------------------------------------------------------

    def apply(self, plans: list[ArtifactPlan]) -> list[ArtifactResult]:
        """Выполнить план: рендер + запись для активных артефактов."""
        results: list[ArtifactResult] = []
        for plan in plans:
            if plan.action == "skip":
                results.append(ArtifactResult(path=plan.target, status="skipped"))
            elif plan.action == "error":
                results.append(ArtifactResult(path=plan.target, status="error", error=plan.error))
            else:  # "create" | "overwrite"
                try:
                    content = self._render(plan.artifact)
                    plan.target.parent.mkdir(parents=True, exist_ok=True)
                    plan.target.write_text(content, encoding="utf-8")
                    status = "overwritten" if plan.action == "overwrite" else "created"
                    results.append(ArtifactResult(path=plan.target, status=status))
                except TemplateNotFound as exc:
                    results.append(ArtifactResult(
                        path=plan.target,
                        status="error",
                        error=t("artifacts.preflight.template_missing", template=str(exc)),
                    ))
                except Exception as exc:
                    results.append(ArtifactResult(path=plan.target, status="error", error=str(exc)))

        return results

    # ---------------------------------------------------------------------------
    # Run (ярлык: plan → apply)
    # ---------------------------------------------------------------------------

    def run(self) -> list[ArtifactResult]:
        """Запустить pipeline: plan() → apply() → результаты."""
        return self.apply(self.plan())

    # ---------------------------------------------------------------------------
    # Render
    # ---------------------------------------------------------------------------

    def _render(self, artifact: ArtifactDef) -> str:
        """Отрендерить содержимое артефакта в зависимости от source_type."""
        if artifact.source_type == ArtifactSourceType.TEMPLATE:
            return self._render_template(artifact)
        elif artifact.source_type == ArtifactSourceType.STATIC:
            if artifact.static_content is None:
                raise ValueError(f"static_content is None for artifact: {artifact.relative_path}")
            return artifact.static_content
        elif artifact.source_type == ArtifactSourceType.PYTHON:
            if artifact.renderer is None:
                raise ValueError(f"renderer is None for artifact: {artifact.relative_path}")
            return artifact.renderer(self.context)
        else:
            raise ValueError(f"Unknown source_type: {artifact.source_type}")

    def _render_template(self, artifact: ArtifactDef) -> str:
        """Отрендерить Jinja2-шаблон с полным контекстом + extra_vars."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATES_DIR)),
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(artifact.source_template)
        ctx = {**self.context.as_template_vars(), **artifact.extra_vars}
        return template.render(**ctx)

    # ---------------------------------------------------------------------------
    # Вывод результатов пользователю
    # ---------------------------------------------------------------------------

    @staticmethod
    def print_results(results: list[ArtifactResult], console: Any) -> None:
        """Вывести понятный отчёт о сгенерированных артефактах."""
        if not results:
            return

        console.print()
        console.print(t("artifacts.header"))

        for r in results:
            path_str = str(r.path)
            if r.status == "created":
                console.print(t("artifacts.created", path=path_str))
            elif r.status == "overwritten":
                console.print(t("artifacts.overwritten", path=path_str))
            elif r.status == "skipped":
                console.print(t("artifacts.skipped", path=path_str))
            elif r.status == "error":
                console.print(t("artifacts.error", path=path_str, error=r.error))

    @staticmethod
    def has_errors(results: list[ArtifactResult]) -> bool:
        """Вернуть True если хотя бы один артефакт завершился с ошибкой."""
        return any(r.has_error for r in results)

