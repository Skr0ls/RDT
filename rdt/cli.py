"""
CLI точка входа для RDT (Rambo Docker Tools).
Команды: init, add, list, up, lang
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
from rdt.i18n import t
import rdt.i18n as i18n

app = typer.Typer(
    name="rdt",
    help=t("app.help"),
    rich_markup_mode="rich",
)
console = Console()

COMPOSE_FILE = Path("docker-compose.yml")
ENV_FILE = Path(".env")
ENV_EXAMPLE_FILE = Path(".env.example")


# ─────────────────────────────────────────────────────────────────────────────
# Callback — запускает интерактивное меню при rdt без аргументов
# ─────────────────────────────────────────────────────────────────────────────
@app.callback(invoke_without_command=True, help=t("app.callback_help"))
def main(ctx: typer.Context) -> None:
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

        elif action == "lang":
            _change_language()
            continue  # Меню сразу перерисуется с новым языком

        console.print()
        cont = questionary.confirm(t("msg.do_more"), default=False).ask()
        if not cont:
            break


def _change_language() -> None:
    """Интерактивная смена языка прямо внутри сессии."""
    langs = i18n.available_langs()
    current = i18n.current_lang()
    choices = [
        questionary.Choice(f"{lang}  ✓" if lang == current else lang, value=lang)
        for lang in langs
    ]
    selected = questionary.select(t("menu.lang_choose"), choices=choices).ask()
    if selected and selected != current:
        i18n.set_lang(selected)
        i18n.reload()
        console.print(t("lang.changed", lang=selected))


# ─────────────────────────────────────────────────────────────────────────────
# rdt init
# ─────────────────────────────────────────────────────────────────────────────
@app.command(help=t("cmd.init.help"))
def init(
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.init.opt_file"))] = COMPOSE_FILE,
    force: Annotated[bool, typer.Option("--force", help=t("cmd.init.opt_force"))] = False,
) -> None:
    if file.exists() and not force:
        console.print(t("msg.file_exists", file=file))
        raise typer.Exit(1)

    data = make_base_compose()
    save_compose(file, data)
    console.print(t("msg.compose_created", file=file))

    # Инициализировать .env и .env.example если не существуют
    if not ENV_FILE.exists():
        ENV_FILE.touch()
        console.print(t("msg.env_created", file=ENV_FILE))
    if not ENV_EXAMPLE_FILE.exists():
        ENV_EXAMPLE_FILE.touch()
        console.print(t("msg.env_created", file=ENV_EXAMPLE_FILE))


# ─────────────────────────────────────────────────────────────────────────────
# rdt add
# ─────────────────────────────────────────────────────────────────────────────
@app.command(help=t("cmd.add.help"))
def add(
    service: Annotated[str, typer.Argument(help=t("cmd.add.arg_service"))],
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.add.opt_file"))] = COMPOSE_FILE,
    hardcore: Annotated[bool, typer.Option("--hardcore", help=t("cmd.add.opt_hardcore"))] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=t("cmd.add.opt_yes"))] = False,
    port: Annotated[Optional[int], typer.Option("--port", "-p", help=t("cmd.add.opt_port"))] = None,
    volume: Annotated[Optional[str], typer.Option("--volume", help=t("cmd.add.opt_volume"))] = None,
    depends_on: Annotated[Optional[list[str]], typer.Option("--depends-on", help=t("cmd.add.opt_depends_on"))] = None,
) -> None:
    service = service.lower()
    preset = ALL_PRESETS.get(service)
    if preset is None:
        console.print(t("msg.service_unknown", service=service))
        console.print(t("msg.use_rdt_list"))
        raise typer.Exit(1)

    # Загрузить или создать файл
    if not file.exists():
        console.print(t("msg.compose_not_found_create", file=file))
        data = make_base_compose()
    else:
        data = load_compose(file)

    existing = get_existing_services(data)

    # Проверить что сервис не добавлен дважды
    container_name = preset.name
    if container_name in existing:
        console.print(t("msg.file_exists", file=f"{container_name} in {file}"))
        raise typer.Exit(1)

    # Режим с мастером или без
    script_mode = yes or port is not None or volume is not None or depends_on is not None
    if script_mode:
        console.print(t("msg.adding_service_script", name=preset.display_name))
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

    console.print(t("msg.service_added", name=preset.display_name, file=file))
    if env_values:
        console.print(t("msg.env_written", file=ENV_FILE))


# ─────────────────────────────────────────────────────────────────────────────
# rdt list
# ─────────────────────────────────────────────────────────────────────────────
@app.command(name="list", help=t("cmd.list.help"))
def list_presets() -> None:
    categories: dict[str, list[ServicePreset]] = {}
    for preset in ALL_PRESETS.values():
        categories.setdefault(preset.category, []).append(preset)

    table = Table(title=t("table.title"), box=box.ROUNDED, show_lines=True)
    table.add_column(t("table.col_category"), style="cyan bold", no_wrap=True)
    table.add_column(t("table.col_command"), style="green")
    table.add_column(t("table.col_service"), style="white")
    table.add_column(t("table.col_image"), style="dim")
    table.add_column(t("table.col_port"), style="yellow", justify="right")

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
@app.command(help=t("cmd.up.help"))
def up(
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.up.opt_file"))] = COMPOSE_FILE,
    detach: Annotated[bool, typer.Option("--detach/--no-detach", "-d", help=t("cmd.up.opt_detach"))] = True,
) -> None:
    if not file.exists():
        console.print(t("msg.compose_not_found_run", file=file))
        raise typer.Exit(1)

    cmd = ["docker", "compose", "-f", str(file), "up"]
    if detach:
        cmd.append("-d")

    console.print(t("msg.running_cmd", cmd=" ".join(cmd)))
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ─────────────────────────────────────────────────────────────────────────────
# rdt lang
# ─────────────────────────────────────────────────────────────────────────────
@app.command(name="lang", help=t("cmd.lang.help"))
def lang_cmd(
    action: Annotated[Optional[str], typer.Argument(help=t("cmd.lang.arg_action"))] = None,
    value: Annotated[Optional[str], typer.Argument(help=t("cmd.lang.arg_value"))] = None,
) -> None:
    # Без аргументов — интерактивный выбор языка
    if action is None:
        _change_language()
        return

    if action == "list":
        console.print(t("lang.current", lang=i18n.current_lang()))
        console.print(t("lang.available"))
        for lang in i18n.available_langs():
            marker = "  ✓" if lang == i18n.current_lang() else ""
            console.print(f"  [green]{lang}[/]{marker}")
        return

    if action == "set":
        if value is None:
            console.print(t("lang.missing_value"))
            raise typer.Exit(1)
        if i18n.set_lang(value):
            console.print(t("lang.changed", lang=value))
        else:
            console.print(t("lang.unknown", lang=value))
            console.print(t("lang.available_list", langs=", ".join(i18n.available_langs())))
            raise typer.Exit(1)
        return

    # Неизвестное действие
    console.print(t("lang.unknown", lang=action))
    raise typer.Exit(1)


if __name__ == "__main__":
    app()

