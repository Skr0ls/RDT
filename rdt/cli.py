"""
CLI точка входа для RDT (Rambo Docker Tools).
Команды: init, add, list, up
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import questionary
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from rdt.presets.catalog import ALL_PRESETS, ServicePreset
from rdt.strategies.factory import get_strategy
from rdt.yaml_manager import load_compose, save_compose, make_base_compose, inject_service, get_existing_services
from rdt.env_manager import get_env_values, write_env, write_env_example
from rdt.wizard import run_wizard, run_main_menu, ask_service_choice, build_script_answers

app = typer.Typer(
    name="rdt",
    help="[bold cyan]Rambo Docker Tools[/] — генератор docker-compose.yml",
    rich_markup_mode="rich",
)
console = Console()

COMPOSE_FILE = Path("docker-compose.yml")
ENV_FILE = Path(".env")
ENV_EXAMPLE_FILE = Path(".env.example")


# ─────────────────────────────────────────────────────────────────────────────
# Callback — запускает интерактивное меню при rdt без аргументов
# ─────────────────────────────────────────────────────────────────────────────
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """[bold cyan]Rambo Docker Tools[/] — генератор docker-compose.yml

    Запустите [green]rdt[/] без аргументов для интерактивного меню
    или используйте подкоманды напрямую.
    """
    if ctx.invoked_subcommand is None:
        _run_interactive()


def _run_interactive() -> None:
    """Запустить главное интерактивное меню."""
    while True:
        action = run_main_menu()

        if action == "exit":
            raise typer.Exit(0)

        elif action == "list":
            list_presets()

        elif action == "init":
            try:
                init()
            except SystemExit:
                pass

        elif action == "up":
            up()
            return

        elif action == "add":
            service_name = ask_service_choice()
            if service_name:
                try:
                    add(service=service_name)
                except SystemExit:
                    pass

        console.print()
        cont = questionary.confirm("Сделать что-то ещё?", default=False).ask()
        if not cont:
            break


# ─────────────────────────────────────────────────────────────────────────────
# rdt init
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def init(
    file: Annotated[Path, typer.Option("--file", "-f", help="Путь к файлу")] = COMPOSE_FILE,
    force: Annotated[bool, typer.Option("--force", help="Перезаписать если существует")] = False,
) -> None:
    """Создать базовый docker-compose.yml с сетью rambo-net."""
    if file.exists() and not force:
        console.print(f"[yellow]⚠  {file} уже существует. Используйте --force для перезаписи.[/]")
        raise typer.Exit(1)

    data = make_base_compose()
    save_compose(file, data)
    console.print(f"[green]✓[/] Создан [bold]{file}[/] с сетью [cyan]rambo-net[/]")

    # Инициализировать .env и .env.example если не существуют
    if not ENV_FILE.exists():
        ENV_FILE.touch()
        console.print(f"[green]✓[/] Создан пустой [bold]{ENV_FILE}[/]")
    if not ENV_EXAMPLE_FILE.exists():
        ENV_EXAMPLE_FILE.touch()
        console.print(f"[green]✓[/] Создан пустой [bold]{ENV_EXAMPLE_FILE}[/]")


# ─────────────────────────────────────────────────────────────────────────────
# rdt add
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def add(
    service: Annotated[str, typer.Argument(help="Имя сервиса (например: postgres, redis, kafka)")],
    file: Annotated[Path, typer.Option("--file", "-f", help="Путь к docker-compose.yml")] = COMPOSE_FILE,
    hardcore: Annotated[bool, typer.Option("--hardcore", help="Генерировать уникальные пароли")] = False,
    # ── Режим без мастера (для скриптинга) ───────────────────────────────────
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Не запускать мастер, использовать значения по умолчанию")] = False,
    port: Annotated[Optional[int], typer.Option("--port", "-p", help="Внешний порт сервиса")] = None,
    volume: Annotated[Optional[str], typer.Option("--volume", help="Volume или путь для данных (например: ./data/pg)")] = None,
    depends_on: Annotated[Optional[list[str]], typer.Option("--depends-on", help="Зависимость (можно указать несколько раз)")] = None,
) -> None:
    """Добавить сервис в docker-compose.yml.

    По умолчанию запускает интерактивный мастер настройки.
    С флагом [green]--yes[/] (-y) пропускает все вопросы и использует значения по умолчанию.

    [bold]Примеры (скрипт-режим):[/]

      rdt add postgres --yes

      rdt add postgres --yes --port 5433 --volume ./data/pg

      rdt add redis --yes --depends-on rdt-postgres --depends-on rdt-rabbitmq

      rdt add postgres --hardcore --yes
    """
    service = service.lower()
    preset = ALL_PRESETS.get(service)
    if preset is None:
        console.print(f"[red]✗[/] Неизвестный сервис: [bold]{service}[/]")
        console.print("Используйте [cyan]rdt list[/] для просмотра доступных сервисов.")
        raise typer.Exit(1)

    # Загрузить или создать файл
    if not file.exists():
        console.print(f"[yellow]⚠  {file} не найден. Создаю базовый файл...[/]")
        data = make_base_compose()
    else:
        data = load_compose(file)

    existing = get_existing_services(data)

    # Проверить что сервис не добавлен дважды
    container_name = preset.name
    if container_name in existing:
        console.print(f"[yellow]⚠  Сервис [bold]{container_name}[/] уже присутствует в {file}[/]")
        raise typer.Exit(1)

    # Режим с мастером или без
    script_mode = yes or port is not None or volume is not None or depends_on is not None
    if script_mode:
        console.print(f"\n[bold cyan]⚙  Добавление сервиса: {preset.display_name}[/] [dim](скрипт-режим)[/]\n")
        answers = build_script_answers(
            preset=preset,
            port=port,
            volume=volume,
            depends_on=depends_on or [],
            hardcore=hardcore,
            existing_services=existing,
        )
    else:
        answers = run_wizard(preset, existing, hardcore=hardcore)

    # Получить значения переменных окружения
    env_values = get_env_values(preset.default_env, hardcore=hardcore or not answers.get("use_default_creds", True))

    # Применить стратегию
    strategy = get_strategy(preset, answers)
    service_def = strategy.build()

    # Вставить сервис в compose
    data = inject_service(data, container_name, service_def)
    save_compose(file, data)

    # Обновить .env и .env.example
    write_env(ENV_FILE, env_values)
    write_env_example(ENV_EXAMPLE_FILE, env_values)

    console.print(f"\n[green]✓[/] Сервис [bold cyan]{preset.display_name}[/] добавлен в [bold]{file}[/]")
    if env_values:
        console.print(f"[green]✓[/] Переменные окружения записаны в [bold]{ENV_FILE}[/]")


# ─────────────────────────────────────────────────────────────────────────────
# rdt list
# ─────────────────────────────────────────────────────────────────────────────
@app.command(name="list")
def list_presets() -> None:
    """Показать все доступные пресеты по категориям."""
    categories: dict[str, list[ServicePreset]] = {}
    for preset in ALL_PRESETS.values():
        categories.setdefault(preset.category, []).append(preset)

    table = Table(title="🐳 RDT — Доступные сервисы", box=box.ROUNDED, show_lines=True)
    table.add_column("Категория", style="cyan bold", no_wrap=True)
    table.add_column("Команда", style="green")
    table.add_column("Сервис", style="white")
    table.add_column("Image", style="dim")
    table.add_column("Порт", style="yellow", justify="right")

    for category, presets in categories.items():
        for i, p in enumerate(presets):
            table.add_row(
                category if i == 0 else "",
                f"rdt add {p.name}",
                p.display_name,
                p.image,
                str(p.default_port),
            )

    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# rdt up
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def up(
    file: Annotated[Path, typer.Option("--file", "-f", help="Путь к docker-compose.yml")] = COMPOSE_FILE,
    detach: Annotated[bool, typer.Option("--detach/--no-detach", "-d", help="Фоновый режим")] = True,
) -> None:
    """Запустить docker compose up (прокси-команда)."""
    if not file.exists():
        console.print(f"[red]✗[/] Файл [bold]{file}[/] не найден. Сначала выполните [cyan]rdt init[/]")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "-f", str(file), "up"]
    if detach:
        cmd.append("-d")

    console.print(f"[cyan]▶[/] Выполняю: [bold]{' '.join(cmd)}[/]\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    app()

