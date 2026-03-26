"""
Подсистема companion-артефактов RDT.

Позволяет сервисам генерировать дополнительные файлы конфигурации
(nginx.conf, logstash.conf, prometheus.yml и т.д.) вместе с compose-блоком.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from rdt.i18n import t


# ---------------------------------------------------------------------------
# Политика перезаписи
# ---------------------------------------------------------------------------

class OverwritePolicy(str, Enum):
    SKIP = "skip"           # не перезаписывать если файл уже существует
    OVERWRITE = "overwrite"  # всегда перезаписывать


# ---------------------------------------------------------------------------
# Модель описания артефакта
# ---------------------------------------------------------------------------

@dataclass
class ArtifactDef:
    """Описание companion-файла, генерируемого вместе с сервисом."""

    relative_path: str
    """Куда записать файл относительно cwd (например: 'nginx/nginx.conf')."""

    source_template: str
    """Путь к Jinja2-шаблону относительно rdt/templates/artifacts/."""

    overwrite: OverwritePolicy = OverwritePolicy.SKIP
    """Политика поведения при существующем файле."""

    condition: str | None = None
    """Ключ в answers — если задан, генерировать только если answers[condition] truthy."""

    extra_vars: dict[str, Any] = field(default_factory=dict)
    """Дополнительные переменные, передаваемые в шаблон поверх answers."""


# ---------------------------------------------------------------------------
# Результат генерации
# ---------------------------------------------------------------------------

@dataclass
class ArtifactResult:
    """Результат генерации одного артефакта."""

    path: Path
    status: str  # "created" | "skipped" | "overwritten" | "error"
    error: str | None = None


# ---------------------------------------------------------------------------
# Pipeline генерации артефактов
# ---------------------------------------------------------------------------

class ArtifactPipeline:
    """
    Pipeline генерации companion-файлов сервиса.

    Алгоритм:
    1. Собрать список артефактов из preset-а
    2. Проверить условие генерации каждого
    3. Проверить существование целевого файла
    4. Отрендерить шаблон через Jinja2
    5. Безопасно записать файл
    6. Вернуть список результатов
    """

    #: Директория с шаблонами артефактов (внутри пакета rdt)
    TEMPLATES_DIR: Path = Path(__file__).parent / "templates" / "artifacts"

    def __init__(
        self,
        artifacts: list[ArtifactDef],
        answers: dict[str, Any],
        base_dir: Path | None = None,
    ) -> None:
        self.artifacts = artifacts
        self.answers = answers
        self.base_dir = base_dir or Path.cwd()

    def run(self) -> list[ArtifactResult]:
        """Запустить pipeline и вернуть результаты по каждому артефакту."""
        results: list[ArtifactResult] = []
        for artifact in self.artifacts:
            # Проверить условие генерации
            if artifact.condition and not self.answers.get(artifact.condition):
                continue
            results.append(self._process(artifact))
        return results

    def _process(self, artifact: ArtifactDef) -> ArtifactResult:
        """Обработать один артефакт: проверить → отрендерить → записать."""
        target = self.base_dir / artifact.relative_path
        already_exists = target.exists()

        # Safe write policy
        if already_exists and artifact.overwrite == OverwritePolicy.SKIP:
            return ArtifactResult(path=target, status="skipped")

        try:
            content = self._render(artifact)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            status = "overwritten" if already_exists else "created"
            return ArtifactResult(path=target, status=status)
        except Exception as exc:
            return ArtifactResult(path=target, status="error", error=str(exc))

    def _render(self, artifact: ArtifactDef) -> str:
        """Отрендерить Jinja2-шаблон с переменными из answers + extra_vars."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATES_DIR)),
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(artifact.source_template)
        ctx = {**self.answers, **artifact.extra_vars}
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

