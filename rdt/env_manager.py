"""
Управление .env и .env.example файлами.
"""
from __future__ import annotations
import os
import secrets
import string
from pathlib import Path

DEFAULT_USER = "rambo"
DEFAULT_PASSWORD = "rambo_password"

# Переменные, которые считаются секретами (выносятся в .env)
_PASSWORD_KEYS = {"PASSWORD", "SECRET", "PASS", "KEY", "TOKEN"}


def is_secret_key(key: str) -> bool:
    return any(k in key.upper() for k in _PASSWORD_KEYS)


def generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_env_values(preset_env: dict[str, str], hardcore: bool) -> dict[str, str]:
    """
    Возвращает конкретные значения для .env переменных.
    hardcore=True → генерировать уникальные пароли.
    """
    result: dict[str, str] = {}
    for key, placeholder in preset_env.items():
        if "${" not in str(placeholder):
            continue
        var_name = str(placeholder).strip("${}").strip()
        if is_secret_key(var_name):
            result[var_name] = generate_password() if hardcore else DEFAULT_PASSWORD
        elif "USER" in var_name.upper():
            result[var_name] = DEFAULT_USER
        elif "EMAIL" in var_name.upper():
            result[var_name] = "admin@rambo.local"
        elif "DB" in var_name.upper() or "DATABASE" in var_name.upper():
            result[var_name] = "rambo_db"
        else:
            result[var_name] = "rambo"
    return result


def write_env(env_path: Path, values: dict[str, str]) -> None:
    """Дописать недостающие переменные в .env файл."""
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    new_vars = {k: v for k, v in values.items() if k not in existing}
    if not new_vars:
        return

    with env_path.open("a", encoding="utf-8") as f:
        f.write("\n")
        for k, v in new_vars.items():
            f.write(f"{k}={v}\n")


def write_env_example(example_path: Path, values: dict[str, str]) -> None:
    """Записать/обновить .env.example с пустыми значениями."""
    existing_keys: set[str] = set()
    if example_path.exists():
        for line in example_path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                existing_keys.add(line.split("=")[0].strip())

    new_vars = {k: "" for k in values if k not in existing_keys}
    if not new_vars:
        return

    with example_path.open("a", encoding="utf-8") as f:
        f.write("\n")
        for k in new_vars:
            f.write(f"{k}=\n")

