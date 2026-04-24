"""
RDT companion artifact subsystem.

Allows services to generate additional configuration files
(nginx.conf, logstash.conf, prometheus.yml, etc.) together with the compose block.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from rdt.i18n import t


# ---------------------------------------------------------------------------
# Overwrite policy
# ---------------------------------------------------------------------------

class OverwritePolicy(str, Enum):
    SKIP = "skip"                       # Do not overwrite when the file already exists.
    OVERWRITE = "overwrite"             # Always overwrite.
    ERROR_IF_EXISTS = "error_if_exists" # Return an error when the file already exists.


# ---------------------------------------------------------------------------
# Artifact source type
# ---------------------------------------------------------------------------

class ArtifactSourceType(str, Enum):
    TEMPLATE = "template"  # Jinja2 template from templates/artifacts/.
    STATIC = "static"      # Static text embedded in ArtifactDef.
    PYTHON = "python"      # Python renderer: (context: ArtifactContext) -> str.


# ---------------------------------------------------------------------------
# Rich artifact-generation context
# ---------------------------------------------------------------------------

@dataclass
class ArtifactContext:
    """
    Full context for generating service companion artifacts.

    Passed to ArtifactPipeline instead of a raw answers dict.
    Available in Jinja2 templates and Python renderers.
    """

    service_name: str
    """Service name (docker-compose key, for example 'nginx-proxy')."""

    answers: dict[str, Any]
    """Wizard or script-mode answers."""

    env_values: dict[str, str]
    """Environment variable values written to .env."""

    project_root: Path
    """Project root used as the base for all artifact paths."""

    compose_file: Path
    """Absolute path to docker-compose.yml."""

    preset: Any = None
    """ServicePreset (Any avoids a circular import from presets/catalog.py)."""

    smart_env: dict[str, Any] = field(default_factory=dict)
    """Environment variables set by Smart Mapping (subset of answers['smart_env'])."""

    depends_on: list[str] = field(default_factory=list)
    """Service dependencies set by Smart Mapping (subset of answers['depends_on'])."""

    parent_service: str | None = None
    """Parent service name when Smart Mapping finds a related service."""

    service_def: dict[str, Any] | None = None
    """Built service-block dictionary (result of strategy.build())."""

    def as_template_vars(self) -> dict[str, Any]:
        """
        Return all variables for Jinja2 rendering.
        Includes answers plus service context fields.
        """
        base: dict[str, Any] = {**self.answers}
        base["service_name"] = self.service_name
        base["project_root"] = str(self.project_root)
        base["compose_file"] = str(self.compose_file)
        base["env_values"] = self.env_values
        base["smart_env"] = self.smart_env
        base["depends_on"] = self.depends_on
        base["parent_service"] = self.parent_service
        if self.service_def is not None:
            base["service_def"] = self.service_def
        if self.preset is not None:
            base["preset_name"] = self.preset.name
            base["preset_display_name"] = self.preset.display_name
        return base


# ---------------------------------------------------------------------------
# Artifact definition model
# ---------------------------------------------------------------------------

@dataclass
class ArtifactDef:
    """Definition of a companion file generated together with a service."""

    relative_path: str
    """Where to write the file relative to project_root (for example: 'nginx/nginx.conf')."""

    source_template: str | None = None
    """Path to a Jinja2 template under rdt/templates/artifacts/. Used when source_type=TEMPLATE."""

    source_type: ArtifactSourceType = ArtifactSourceType.TEMPLATE
    """File content source type."""

    static_content: str | None = None
    """Ready-to-write file content. Used when source_type=STATIC."""

    renderer: Callable[[ArtifactContext], str] | None = None
    """Python renderer. Used when source_type=PYTHON."""

    overwrite: OverwritePolicy = OverwritePolicy.SKIP
    """Behavior policy for existing files."""

    condition: str | None = None
    """answers key; generate only when answers[condition] is truthy."""

    extra_vars: dict[str, Any] = field(default_factory=dict)
    """Additional template variables layered over context.as_template_vars()."""


# ---------------------------------------------------------------------------
# Preflight check result
# ---------------------------------------------------------------------------

@dataclass
class PreflightIssue:
    """One issue found during preflight checks."""
    artifact_path: str
    reason: str


# ---------------------------------------------------------------------------
# Generation result
# ---------------------------------------------------------------------------

@dataclass
class ArtifactResult:
    """Generation result for one artifact."""

    path: Path
    status: str  # "created" | "skipped" | "overwritten" | "error"
    error: str | None = None

    @property
    def has_error(self) -> bool:
        return self.status == "error"


# ---------------------------------------------------------------------------
# Planned action (plan → apply)
# ---------------------------------------------------------------------------

@dataclass
class ArtifactPlan:
    """Planned action for one artifact before writing anything."""

    artifact: ArtifactDef
    target: Path
    action: Literal["create", "overwrite", "skip", "error"]
    error: str | None = None


# ---------------------------------------------------------------------------
# Artifact generation pipeline
# ---------------------------------------------------------------------------

class ArtifactPipeline:
    """
    Pipeline for generating service companion files.

    plan → apply architecture:
    1. preflight() — check templates, paths, and policies before writing
    2. plan()      — build a list of planned actions without writing
    3. apply()     — execute the plan: render + write files
    4. run()       — shortcut for plan() → apply()
    """

    #: Directory containing artifact templates inside the rdt package.
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
        """Project root from the context."""
        return self.context.project_root

    # ---------------------------------------------------------------------------
    # Preflight
    # ---------------------------------------------------------------------------

    def preflight(self) -> list[PreflightIssue]:
        """
        Check whether all active artifacts are ready to generate.
        Returns found issues; an empty list means everything is okay.
        """
        issues: list[PreflightIssue] = []
        for artifact in self.artifacts:
            # Skip when the condition is not satisfied.
            if artifact.condition and not self.context.answers.get(artifact.condition):
                continue

            target = self.base_dir / artifact.relative_path

            # 1. Check the content source.
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

            # 2. Check the existing-file policy.
            if target.exists() and artifact.overwrite == OverwritePolicy.ERROR_IF_EXISTS:
                issues.append(PreflightIssue(
                    artifact_path=artifact.relative_path,
                    reason=t("artifacts.preflight.file_exists", path=str(target)),
                ))

            # 3. Check parent directory availability when it already exists.
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
        Determine what will happen to each active artifact without writing anything.
        Returns ArtifactPlan entries with action: create | overwrite | skip | error.
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
        """Execute the plan: render and write active artifacts."""
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
    # Run (shortcut: plan → apply)
    # ---------------------------------------------------------------------------

    def run(self) -> list[ArtifactResult]:
        """Run the pipeline: plan() → apply() → results."""
        return self.apply(self.plan())

    # ---------------------------------------------------------------------------
    # Render
    # ---------------------------------------------------------------------------

    def _render(self, artifact: ArtifactDef) -> str:
        """Render artifact content according to source_type."""
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
        """Render a Jinja2 template with the full context plus extra_vars."""
        env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATES_DIR)),
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(artifact.source_template)
        ctx = {**self.context.as_template_vars(), **artifact.extra_vars}
        return template.render(**ctx)

    # ---------------------------------------------------------------------------
    # User-facing result output
    # ---------------------------------------------------------------------------

    @staticmethod
    def print_results(results: list[ArtifactResult], console: Any) -> None:
        """Print a readable report for generated artifacts."""
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
        """Return True when at least one artifact failed."""
        return any(r.has_error for r in results)


# ---------------------------------------------------------------------------
# P2: Bootstrap Hint — user guidance for manual steps
# ---------------------------------------------------------------------------

@dataclass
class BootstrapHint:
    """
    Hint about manual steps to perform after adding a service.

    Used for instructions that cannot be automated, such as running an
    initialization command inside a container. Intentionally displayed only;
    RDT does not execute these steps automatically.
    """

    message: str
    """Hint text describing what should be done."""

    command: str | None = None
    """Optional command to display for reference only; RDT does not execute it."""


# ---------------------------------------------------------------------------
# P2: Directory Scaffolding — declarative directory creation
# ---------------------------------------------------------------------------

@dataclass
class DirectoryDef:
    """
    Definition of a directory to create during scaffolding.

    Used to declare project structure that should exist before specific files
    (artifacts) are written into it. Examples: logstash/pipeline/, logstash/config/.
    """

    relative_path: str
    """Directory path relative to project_root."""


@dataclass
class ScaffoldPlan:
    """Planned action for one directory before creation."""

    directory: DirectoryDef
    target: Path
    action: Literal["create", "skip"]
    """create means the directory will be created; skip means it already exists."""


@dataclass
class ScaffoldResult:
    """Result of creating one directory during scaffolding."""

    path: Path
    status: str  # "created" | "already_exists" | "error"
    error: str | None = None

    @property
    def has_error(self) -> bool:
        return self.status == "error"


class ScaffoldPipeline:
    """
    Pipeline for declarative directory creation.

    plan → apply architecture:
    1. plan()  — determine which directories to create without writing
    2. apply() — create directories according to the plan
    3. run()   — shortcut for plan() → apply()
    """

    def __init__(self, directories: list[DirectoryDef], project_root: Path) -> None:
        self.directories = directories
        self.project_root = project_root

    def plan(self) -> list[ScaffoldPlan]:
        """Determine the action for each directory without creating anything."""
        plans: list[ScaffoldPlan] = []
        for dir_def in self.directories:
            target = self.project_root / dir_def.relative_path
            action: Literal["create", "skip"] = "skip" if target.exists() else "create"
            plans.append(ScaffoldPlan(directory=dir_def, target=target, action=action))
        return plans

    def apply(self, plans: list[ScaffoldPlan]) -> list[ScaffoldResult]:
        """Execute the plan: create directories and return results."""
        results: list[ScaffoldResult] = []
        for plan in plans:
            if plan.action == "skip":
                results.append(ScaffoldResult(path=plan.target, status="already_exists"))
            else:
                try:
                    plan.target.mkdir(parents=True, exist_ok=True)
                    results.append(ScaffoldResult(path=plan.target, status="created"))
                except Exception as exc:
                    results.append(ScaffoldResult(path=plan.target, status="error", error=str(exc)))
        return results

    def run(self) -> list[ScaffoldResult]:
        """Run the pipeline: plan() → apply() → results."""
        return self.apply(self.plan())

    @staticmethod
    def has_errors(results: list[ScaffoldResult]) -> bool:
        """Return True when at least one directory operation failed."""
        return any(r.has_error for r in results)

    @staticmethod
    def print_results(results: list[ScaffoldResult], console: Any) -> None:
        """Print a readable report for scaffolding operations."""
        if not results:
            return
        console.print()
        console.print(t("scaffold.header"))
        for r in results:
            path_str = str(r.path)
            if r.status == "created":
                console.print(t("scaffold.created", path=path_str))
            elif r.status == "already_exists":
                console.print(t("scaffold.already_exists", path=path_str))
            elif r.status == "error":
                console.print(t("scaffold.error", path=path_str, error=r.error))

