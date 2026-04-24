"""
RDT MCP Server — Model Context Protocol server for Rambo Docker Tools.

Transport: stdio (the standard MCP transport).
Run with: rdt-mcp (entry point defined in pyproject.toml).

Tools:
  rdt_init    — initialize docker-compose.yml + .env
  rdt_add     — add a service to the stack
  rdt_remove  — remove a service from the stack
  rdt_list    — list available presets
  rdt_doctor  — run full project diagnostics
  rdt_check   — validate YAML via docker compose config
  rdt_up      — run docker compose up
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from rdt.core import (
    RdtError,
    add,
    check,
    doctor,
    init,
    list_presets,
    remove,
    up,
)
from rdt.yaml_manager import DEFAULT_COMPOSE_FILE, resolve_default_compose_file

# ─────────────────────────────────────────────────────────────────────────────
# Server instance
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "rdt",
    instructions=(
        "RDT (Rambo Docker Tools) generates production-ready docker-compose stacks. "
        "Use rdt_list to inspect available services, rdt_init to initialize a project, "
        "rdt_add to add services, and rdt_doctor to diagnose the stack before startup. "
        "All tools accept project_dir, an absolute path to the working directory. "
        "If project_dir is omitted, the current working directory is used."
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper function
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_file(project_dir: str | None, file: str) -> Path:
    """Resolve a compose-file path relative to project_dir when provided."""
    base = Path(project_dir) if project_dir else Path.cwd()
    p = Path(file)
    resolved = base / p if not p.is_absolute() else p
    return resolve_default_compose_file(resolved) if file == DEFAULT_COMPOSE_FILE else resolved


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def rdt_init(
    file: str = "docker-compose.yml",
    force: bool = False,
    project_dir: str | None = None,
) -> dict[str, Any]:
    """
    Initialize a new docker-compose.yml, .env and .env.example in the project directory.

    Args:
        file: Compose file name or path (default: docker-compose.yml).
        force: Overwrite existing files if True.
        project_dir: Absolute path to the project directory (default: cwd).
    """
    try:
        result = init(_resolve_file(project_dir, file), force=force)
        return {"status": "ok", "file": result.file, "created": result.created}
    except RdtError as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def rdt_add(
    service: str,
    file: str = "docker-compose.yml",
    project_dir: str | None = None,
    port: int | None = None,
    volume: str | None = None,
    depends_on: list[str] | None = None,
    hardcore: bool = False,
    no_ports: bool = False,
    network: str | None = None,
    container_name: str | None = None,
    hc_interval: str | None = None,
    hc_timeout: str | None = None,
    hc_retries: int | None = None,
    hc_start_period: str | None = None,
    set_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Add a service to docker-compose.yml. Always prefer this over editing the file manually.

    Args:
        service: Service name (e.g. postgres, redis, nginx-proxy). Use rdt_list to see all options.
        file: Compose file path (default: docker-compose.yml).
        project_dir: Absolute path to the project directory (default: cwd).
        port: Override the default host port.
        volume: Named volume or bind-mount path (e.g. ./data/pg).
        depends_on: List of service names this service depends on.
        hardcore: Generate strong random passwords instead of defaults.
        no_ports: Expose ports only within the Docker network (not to the host).
        network: Network type or external network name (bridge|host|none|<name>).
        container_name: Explicit container name.
        hc_interval: Healthcheck interval (e.g. 10s).
        hc_timeout: Healthcheck timeout (e.g. 5s).
        hc_retries: Healthcheck retries count.
        hc_start_period: Healthcheck start period (e.g. 30s).
        set_vars: Override any internal wizard variable (e.g. {"nginx_upstream": "app:8080"}).
    """
    try:
        result = add(
            service=service,
            file=_resolve_file(project_dir, file),
            port=port,
            volume=volume,
            depends_on=depends_on,
            hardcore=hardcore,
            no_ports=no_ports,
            network=network,
            container_name=container_name,
            hc_interval=hc_interval,
            hc_timeout=hc_timeout,
            hc_retries=hc_retries,
            hc_start_period=hc_start_period,
            set_vars=set_vars,
        )
        return {
            "status": "ok",
            "service": result.service,
            "port": result.port,
            "env_vars": result.env_vars,
            "artifacts_created": result.artifacts_created,
            "hints": result.hints,
        }
    except RdtError as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def rdt_remove(
    service: str,
    file: str = "docker-compose.yml",
    project_dir: str | None = None,
    clean_env: bool = False,
    clean_artifacts: bool = False,
) -> dict[str, Any]:
    """
    Remove a service from docker-compose.yml.

    Args:
        service: Service name to remove.
        file: Compose file path (default: docker-compose.yml).
        project_dir: Absolute path to the project directory (default: cwd).
        clean_env: Remove orphaned variables from .env file.
        clean_artifacts: Delete companion config files generated for this service.
    """
    try:
        result = remove(
            service=service,
            file=_resolve_file(project_dir, file),
            clean_env=clean_env,
            clean_artifacts=clean_artifacts,
        )
        return {
            "status": "ok",
            "removed": result.removed,
            "removed_volumes": result.removed_volumes,
            "cleaned_env_vars": result.cleaned_env_vars,
            "cleaned_files": result.cleaned_files,
            "dependents_warned": result.dependents_warned,
        }
    except RdtError as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def rdt_list(category: str | None = None) -> dict[str, Any]:
    """
    List all available service presets.

    Args:
        category: Optional filter by category name
                  (e.g. "Relational DB", "NoSQL / Cache", "Monitoring").
    """
    presets = list_presets(category=category)
    return {
        "presets": [
            {
                "name": p.name,
                "display_name": p.display_name,
                "category": p.category,
                "image": p.image,
                "default_port": p.default_port,
                "container_port": p.container_port,
                "has_healthcheck": p.has_healthcheck,
            }
            for p in presets
        ]
    }


@mcp.tool()
def rdt_doctor(
    file: str = "docker-compose.yml",
    project_dir: str | None = None,
) -> dict[str, Any]:
    """
    Run a full diagnostic check on the project.

    Checks: Docker availability, Compose v2, YAML validity, .env completeness,
    port conflicts, dangling depends_on, missing companion files.
    Always run this before finishing a task.

    Args:
        file: Compose file path (default: docker-compose.yml).
        project_dir: Absolute path to the project directory (default: cwd).
    """
    try:
        result = doctor(_resolve_file(project_dir, file))
        return {"checks": result.checks, "summary": result.summary}
    except RdtError as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def rdt_check(
    file: str = "docker-compose.yml",
    project_dir: str | None = None,
) -> dict[str, Any]:
    """
    Validate docker-compose.yml syntax via `docker compose config`.

    Args:
        file: Compose file path (default: docker-compose.yml).
        project_dir: Absolute path to the project directory (default: cwd).
    """
    try:
        result = check(_resolve_file(project_dir, file))
        if result.valid:
            return {"valid": True}
        return {"valid": False, "error": result.error}
    except RdtError as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def rdt_up(
    file: str = "docker-compose.yml",
    project_dir: str | None = None,
    detach: bool = True,
) -> dict[str, Any]:
    """
    Start the Docker Compose stack.
    Do NOT call this unless the user explicitly asks to start the stack.

    Args:
        file: Compose file path (default: docker-compose.yml).
        project_dir: Absolute path to the project directory (default: cwd).
        detach: Run containers in the background (default: True).
    """
    try:
        result = up(_resolve_file(project_dir, file), detach=detach)
        return {"command": result.command, "returncode": result.returncode}
    except RdtError as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
