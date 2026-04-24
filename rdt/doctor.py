"""
rdt doctor — full Docker project diagnostics.

Checks:
  1. Docker is available (docker --version)
  2. Docker Compose v2 is available (docker compose version)
  3. The compose file is valid (docker compose config)
  4. All ${VAR} references in compose are covered by .env values
  5. Ports published by compose are not busy on the host
  6. depends_on does not reference missing services
  7. Bind-mounted files (companion files) exist on disk
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rdt.i18n import t
from rdt.port_utils import is_port_free
from rdt.yaml_manager import load_compose


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    status: str          # "ok" | "warn" | "error" | "skip"
    message: str
    details: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _parse_host_port(port_str: str) -> int | None:
    """Extract the host port from a docker-compose port mapping string."""
    port_str = str(port_str).strip("\"'")
    port_str = re.sub(r"/(tcp|udp)$", "", port_str)
    parts = port_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0])
        if len(parts) == 3:
            return int(parts[1])
    except (ValueError, IndexError):
        pass
    return None


def _load_env_values(env_file: Path) -> dict[str, str]:
    """Load variables from .env without depending on dotenv."""
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — Docker is installed and running
# ─────────────────────────────────────────────────────────────────────────────

def check_docker_available() -> CheckResult:
    try:
        r = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return CheckResult("docker", "ok", t("doctor.docker_ok", version=r.stdout.strip()))
        return CheckResult("docker", "error", t("doctor.docker_not_running"))
    except FileNotFoundError:
        return CheckResult("docker", "error", t("doctor.docker_not_found"))
    except Exception as exc:
        return CheckResult("docker", "error", t("doctor.docker_error", error=str(exc)))


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — Docker Compose v2 is available
# ─────────────────────────────────────────────────────────────────────────────

def check_compose_available() -> CheckResult:
    try:
        r = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return CheckResult("compose", "ok", t("doctor.compose_ok", version=r.stdout.strip()))
        return CheckResult("compose", "error", t("doctor.compose_not_found"))
    except FileNotFoundError:
        return CheckResult("compose", "error", t("doctor.compose_not_found"))
    except Exception as exc:
        return CheckResult("compose", "error", t("doctor.compose_error", error=str(exc)))


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — compose file passes `docker compose config`
# ─────────────────────────────────────────────────────────────────────────────

def check_compose_valid(file: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("compose_valid", "skip", t("doctor.compose_file_missing", file=file))
    try:
        r = subprocess.run(
            ["docker", "compose", "-f", str(file), "config"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            return CheckResult("compose_valid", "ok", t("doctor.compose_valid_ok"))
        details = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        return CheckResult("compose_valid", "error", t("doctor.compose_valid_fail"), details=details)
    except FileNotFoundError:
        return CheckResult("compose_valid", "skip", t("doctor.compose_valid_skip_no_docker"))
    except Exception as exc:
        return CheckResult("compose_valid", "error", t("doctor.compose_valid_error", error=str(exc)))


# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — all ${VAR} references in compose are covered by .env
# ─────────────────────────────────────────────────────────────────────────────

def check_env_vars(file: Path, project_root: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("env_vars", "skip", t("doctor.env_skip_no_compose"))

    compose_text = file.read_text(encoding="utf-8")
    referenced = sorted(set(re.findall(r"\$\{([^}]+)\}", compose_text)))

    if not referenced:
        return CheckResult("env_vars", "ok", t("doctor.env_no_vars"))

    env_values = _load_env_values(project_root / ".env")
    # System environment variables count too.
    for k, v in os.environ.items():
        env_values.setdefault(k, v)

    missing = [v for v in referenced if not env_values.get(v)]

    if not missing:
        return CheckResult("env_vars", "ok", t("doctor.env_ok", count=len(referenced)))
    details = [t("doctor.env_missing_var", var=v) for v in missing]
    return CheckResult("env_vars", "warn", t("doctor.env_missing", count=len(missing)), details=details)


# ─────────────────────────────────────────────────────────────────────────────
# Check 5 — ports published by compose are not busy on the host
# ─────────────────────────────────────────────────────────────────────────────

def check_port_conflicts(file: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("port_conflicts", "skip", t("doctor.port_skip_no_compose"))

    data = load_compose(file)
    services = data.get("services") or {}
    busy: list[tuple[str, int]] = []

    for svc_name, svc_def in services.items():
        if not svc_def:
            continue
        for port_mapping in (svc_def.get("ports") or []):
            hp = _parse_host_port(port_mapping)
            if hp and not is_port_free(hp):
                busy.append((svc_name, hp))

    if not busy:
        return CheckResult("port_conflicts", "ok", t("doctor.port_ok"))
    details = [t("doctor.port_busy_entry", service=svc, port=p) for svc, p in busy]
    return CheckResult("port_conflicts", "warn", t("doctor.port_conflicts", count=len(busy)), details=details)


# ─────────────────────────────────────────────────────────────────────────────
# Check 6 — depends_on does not reference missing services
# ─────────────────────────────────────────────────────────────────────────────

def check_dangling_depends_on(file: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("dangling_deps", "skip", t("doctor.deps_skip_no_compose"))

    data = load_compose(file)
    services = data.get("services") or {}
    known = set(services.keys())
    dangling: list[tuple[str, str]] = []

    for svc_name, svc_def in services.items():
        if not svc_def:
            continue
        raw_deps = svc_def.get("depends_on") or {}
        deps: list[str] = list(raw_deps.keys()) if isinstance(raw_deps, dict) else list(raw_deps)
        for dep in deps:
            if dep not in known:
                dangling.append((svc_name, dep))

    if not dangling:
        return CheckResult("dangling_deps", "ok", t("doctor.deps_ok"))
    details = [t("doctor.deps_dangling_entry", service=svc, dep=dep) for svc, dep in dangling]
    return CheckResult("dangling_deps", "error", t("doctor.deps_dangling", count=len(dangling)), details=details)


# ─────────────────────────────────────────────────────────────────────────────
# Check 7 — bind-mounted files exist
# ─────────────────────────────────────────────────────────────────────────────

def check_companion_files(file: Path, project_root: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("companion_files", "skip", t("doctor.companion_skip_no_compose"))

    data = load_compose(file)
    services = data.get("services") or {}
    missing: list[tuple[str, str]] = []

    def _check_path(svc: str, src: str) -> None:
        # Bind mounts start with . / ..
        if not (src.startswith("./") or src.startswith("../") or (src.startswith("/") and len(src) > 1)):
            return
        resolved = (project_root / src).resolve()
        if resolved.exists():
            return
        # File-like paths (extension or dot in name) are reported as missing companions.
        if resolved.suffix or "." in resolved.name:
            missing.append((svc, src))

    for svc_name, svc_def in services.items():
        if not svc_def:
            continue
        for vol in (svc_def.get("volumes") or []):
            src = str(vol).split(":")[0]
            _check_path(svc_name, src)

    # Top-level configs / secrets.
    for section in ("configs", "secrets"):
        for _key, cfg in (data.get(section) or {}).items():
            if isinstance(cfg, dict) and (src := cfg.get("file")):
                _check_path(f"({section})", src)

    if not missing:
        return CheckResult("companion_files", "ok", t("doctor.companion_ok"))
    details = [t("doctor.companion_missing_entry", service=svc, path=p) for svc, p in missing]
    return CheckResult(
        "companion_files", "warn",
        t("doctor.companion_missing", count=len(missing)),
        details=details,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public aggregator — runs all checks and returns their results
# ─────────────────────────────────────────────────────────────────────────────

def run_all_checks(file: Path, project_root: Path) -> list[CheckResult]:
    return [
        check_docker_available(),
        check_compose_available(),
        check_compose_valid(file),
        check_env_vars(file, project_root),
        check_port_conflicts(file),
        check_dangling_depends_on(file),
        check_companion_files(file, project_root),
    ]

