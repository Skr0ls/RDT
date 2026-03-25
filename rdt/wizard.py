"""
Интерактивный мастер добавления сервиса (Wizard Mode).
"""
from __future__ import annotations
from typing import Any

import questionary
from rich.console import Console

from rdt.presets.catalog import ServicePreset, CATEGORY_RELATIONAL, CATEGORY_NOSQL
from rdt.port_utils import is_port_free, validate_port
from rdt.smart_mapping import get_candidate_parents, apply_smart_mapping

console = Console()

_VOLUME_TYPES = {
    CATEGORY_RELATIONAL: True,
    CATEGORY_NOSQL: True,
}


def run_wizard(
    preset: ServicePreset,
    existing_services: list[str],
    hardcore: bool = False,
) -> dict[str, Any]:
    """
    Запустить интерактивный мастер для выбранного пресета.
    Возвращает словарь answers для передачи в стратегию.
    """
    answers: dict[str, Any] = {}

    console.print(f"\n[bold cyan]⚙  Настройка сервиса: {preset.display_name}[/]\n")

    # ── 1. Порт ──────────────────────────────────────────────────────────────
    answers["port"] = _ask_port(preset)

    # ── 2. Credentials ───────────────────────────────────────────────────────
    if preset.default_env and not hardcore:
        use_default = questionary.confirm(
            f"Использовать стандартные credentials (rambo / rambo_password)?",
            default=True,
        ).ask()
        answers["use_default_creds"] = use_default
    else:
        answers["use_default_creds"] = not hardcore

    # ── 3. Volumes (только для БД) ────────────────────────────────────────────
    if preset.volumes and _needs_volume(preset):
        answers["volume_source"] = _ask_volume(preset)

    # ── 4. depends_on ────────────────────────────────────────────────────────
    if existing_services:
        answers["depends_on"] = _ask_depends_on(existing_services)
    else:
        answers["depends_on"] = []

    # ── 5. Smart Mapping ─────────────────────────────────────────────────────
    candidates = get_candidate_parents(preset.name, existing_services)
    if candidates:
        answers = _ask_smart_mapping(preset.name, candidates, existing_services, answers)

    return answers


def _ask_port(preset: ServicePreset) -> int:
    default_free = is_port_free(preset.default_port)
    default_label = f"{preset.default_port}" + ("" if default_free else " [занят!]")

    choice = questionary.select(
        "Порт:",
        choices=[
            questionary.Choice(f"Стандартный ({default_label})", value="default"),
            questionary.Choice("Ввести вручную", value="custom"),
        ],
    ).ask()

    if choice == "default":
        if not default_free:
            console.print(f"[yellow]⚠  Порт {preset.default_port} занят. Укажите другой.[/]")
            return _ask_custom_port(preset.default_port)
        return preset.default_port
    else:
        return _ask_custom_port(preset.default_port)


def _ask_custom_port(hint: int) -> int:
    while True:
        raw = questionary.text(f"Введите порт (подсказка: {hint}):").ask()
        ok, msg = validate_port(raw or "")
        if ok:
            return int(raw)
        console.print(f"[red]✗ {msg}[/]")


def _needs_volume(preset: ServicePreset) -> bool:
    return bool(preset.volumes)


def _ask_volume(preset: ServicePreset) -> str:
    default_named = f"rdt_{preset.name}_data"
    choice = questionary.select(
        "Хранилище данных (volume):",
        choices=[
            questionary.Choice(f"Именованный volume ({default_named})", value="named"),
            questionary.Choice("Локальная папка (./data/<service>)", value="local"),
        ],
    ).ask()

    if choice == "named":
        return default_named
    else:
        return f"./data/{preset.name}"


def _ask_depends_on(existing_services: list[str]) -> list[str]:
    if not existing_services:
        return []
    choices = questionary.checkbox(
        "Зависимости (depends_on, с условием service_healthy):",
        choices=existing_services,
    ).ask()
    return choices or []


def _ask_smart_mapping(
    service_name: str,
    candidates: list[str],
    existing_services: list[str],
    answers: dict[str, Any],
) -> dict[str, Any]:
    """Предложить выбрать родительский сервис для smart-mapping."""
    labels = {
        "pgadmin": "Postgres",
        "kafka-ui": "Kafka",
        "grafana": "Prometheus",
        "phpmyadmin": "MySQL / MariaDB",
        "mongo-express": "MongoDB",
    }
    parent_label = labels.get(service_name, "родительский сервис")

    console.print(f"\n[bold green]🔗 Smart Mapping[/]: обнаружен {parent_label}")

    if len(candidates) == 1:
        use = questionary.confirm(
            f"Автоматически подключить к [{candidates[0]}]?",
            default=True,
        ).ask()
        if use:
            answers["parent_service"] = candidates[0]
            answers = apply_smart_mapping(service_name, existing_services, answers)
    else:
        selected = questionary.select(
            f"Выберите {parent_label} для подключения:",
            choices=candidates + ["— пропустить —"],
        ).ask()
        if selected != "— пропустить —":
            answers["parent_service"] = selected
            answers = apply_smart_mapping(service_name, existing_services, answers)

    return answers

