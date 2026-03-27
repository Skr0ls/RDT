"""
rdt doctor — полная диагностика Docker-проекта.

Checks:
  1. Docker доступен (docker --version)
  2. Docker Compose v2 доступен (docker compose version)
  3. compose-файл валиден (docker compose config)
  4. Все ${VAR} в compose покрыты значениями из .env
  5. Порты, прокинутые в compose, не заняты на хосте
  6. depends_on не ссылается на несуществующие сервисы
  7. Bind-mounted файлы (companion-файлы) существуют на диске
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
# Типы результатов
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    status: str          # "ok" | "warn" | "error" | "skip"
    message: str
    details: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _parse_host_port(port_str: str) -> int | None:
    """Извлечь host-порт из строки маппинга docker-compose."""
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
    """Загрузить переменные из .env без зависимости от dotenv."""
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
# Проверка 1 — Docker установлен и работает
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
# Проверка 2 — Docker Compose v2 доступен
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
# Проверка 3 — compose-файл проходит `docker compose config`
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
# Проверка 4 — все ${VAR} в compose покрыты значениями из .env
# ─────────────────────────────────────────────────────────────────────────────

def check_env_vars(file: Path, project_root: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("env_vars", "skip", t("doctor.env_skip_no_compose"))

    compose_text = file.read_text(encoding="utf-8")
    referenced = sorted(set(re.findall(r"\$\{([^}]+)\}", compose_text)))

    if not referenced:
        return CheckResult("env_vars", "ok", t("doctor.env_no_vars"))

    env_values = _load_env_values(project_root / ".env")
    # Системные переменные тоже в счёт
    for k, v in os.environ.items():
        env_values.setdefault(k, v)

    missing = [v for v in referenced if not env_values.get(v)]

    if not missing:
        return CheckResult("env_vars", "ok", t("doctor.env_ok", count=len(referenced)))
    details = [t("doctor.env_missing_var", var=v) for v in missing]
    return CheckResult("env_vars", "warn", t("doctor.env_missing", count=len(missing)), details=details)


# ─────────────────────────────────────────────────────────────────────────────
# Проверка 5 — порты, прокинутые в compose, не заняты на хосте
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
# Проверка 6 — depends_on не ссылается на несуществующие сервисы
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
# Проверка 7 — bind-mount'ированные файлы существуют
# ─────────────────────────────────────────────────────────────────────────────

def check_companion_files(file: Path, project_root: Path) -> CheckResult:
    if not file.exists():
        return CheckResult("companion_files", "skip", t("doctor.companion_skip_no_compose"))

    data = load_compose(file)
    services = data.get("services") or {}
    missing: list[tuple[str, str]] = []

    def _check_path(svc: str, src: str) -> None:
        # Bind-mounts: начинаются с . / ..
        if not (src.startswith("./") or src.startswith("../") or (src.startswith("/") and len(src) > 1)):
            return
        resolved = (project_root / src).resolve()
        if resolved.exists():
            return
        # Файлы (с расширением или точкой в имени) — сообщаем как отсутствующий companion
        if resolved.suffix or "." in resolved.name:
            missing.append((svc, src))

    for svc_name, svc_def in services.items():
        if not svc_def:
            continue
        for vol in (svc_def.get("volumes") or []):
            src = str(vol).split(":")[0]
            _check_path(svc_name, src)

    # Верхнеуровневые configs / secrets
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
# Публичный агрегатор — запускает все проверки и возвращает список результатов
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

