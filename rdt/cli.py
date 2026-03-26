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
from rdt.strategies.base import NETWORK_NAME
from rdt.strategies.factory import get_strategy
from rdt.yaml_manager import load_compose, save_compose, make_base_compose, inject_service, get_existing_services, get_services_with_healthcheck
from rdt.env_manager import get_env_values, write_env, write_env_example
from rdt.wizard import run_wizard, run_main_menu, ask_service_choice, build_script_answers
from rdt.artifacts import (
    ArtifactContext, ArtifactPipeline, ArtifactPlan, PreflightIssue,
    ScaffoldPipeline, ScaffoldPlan,
)
from rdt.i18n import t
import rdt.i18n as i18n

app = typer.Typer(
    name="rdt",
    help=t("app.help"),
    rich_markup_mode="rich",
)
console = Console()

COMPOSE_FILE = Path("docker-compose.yml")


def _resolve_project_root(file: Path) -> Path:
    """
    Единое правило определения project root:
    - если --file задан с директорией — root = директория compose-файла
    - иначе root = текущая рабочая директория

    Все выходные файлы (.env, .env.example, artifacts) строятся от этого корня.
    """
    return file.parent.resolve()


# ─────────────────────────────────────────────────────────────────────────────
# Callback — запускает интерактивное меню при rdt без аргументов
# ─────────────────────────────────────────────────────────────────────────────
@app.callback(invoke_without_command=True, help=t("app.callback_help"))
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _run_interactive(ctx)


def _run_interactive(ctx: typer.Context) -> None:
    """Запустить главное интерактивное меню."""
    while True:
        action = run_main_menu()

        if action == "exit":
            raise typer.Exit(0)

        elif action == "help":
            _show_help(ctx)

        elif action == "list":
            list_presets()

        elif action == "init":
            try:
                init()
            except SystemExit:
                pass

        elif action == "check":
            check()

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


def _show_help(ctx: typer.Context) -> None:
    """Вывести полную справку по командам RDT (аналог rdt --help)."""
    console.print(ctx.get_help())


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


def _print_plan_summary(
    file: Path,
    svc_key: str,
    env_file: Path,
    env_values: dict,
    artifact_plans: list[ArtifactPlan],
    compose_file_existed: bool,
    scaffold_plans: list[ScaffoldPlan] | None = None,
) -> None:
    """Вывести сводку запланированных изменений до их применения."""
    console.print(t("plan.header"))
    if not compose_file_existed:
        console.print(t("plan.compose_create", file=file))
    else:
        console.print(t("plan.compose_add_service", name=svc_key, file=file))
    if env_values:
        keys = ", ".join(env_values.keys())
        console.print(t("plan.env_write", file=env_file, keys=keys))
    for sp in (scaffold_plans or []):
        path_str = str(sp.target)
        if sp.action == "create":
            console.print(t("plan.scaffold_create", path=path_str))
        elif sp.action == "skip":
            console.print(t("plan.scaffold_skip", path=path_str))
    for ap in artifact_plans:
        path_str = str(ap.target)
        if ap.action == "create":
            console.print(t("plan.artifact_create", path=path_str))
        elif ap.action == "overwrite":
            console.print(t("plan.artifact_overwrite", path=path_str))
        elif ap.action == "skip":
            console.print(t("plan.artifact_skip", path=path_str))


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

    project_root = _resolve_project_root(file)
    env_file = project_root / ".env"
    env_example_file = project_root / ".env.example"

    data = make_base_compose()
    save_compose(file, data)
    console.print(t("msg.compose_created", file=file))

    # Инициализировать .env и .env.example если не существуют
    if not env_file.exists():
        env_file.touch()
        console.print(t("msg.env_created", file=env_file))
    if not env_example_file.exists():
        env_example_file.touch()
        console.print(t("msg.env_created", file=env_example_file))


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
    container_name_opt: Annotated[Optional[str], typer.Option("--container-name", help=t("cmd.add.opt_container_name"))] = None,
    no_ports: Annotated[bool, typer.Option("--no-ports", help=t("cmd.add.opt_no_ports"))] = False,
    network: Annotated[Optional[str], typer.Option("--network", help=t("cmd.add.opt_network"))] = None,
    hc_interval: Annotated[Optional[str], typer.Option("--hc-interval", help=t("cmd.add.opt_hc_interval"))] = None,
    hc_timeout: Annotated[Optional[str], typer.Option("--hc-timeout", help=t("cmd.add.opt_hc_timeout"))] = None,
    hc_retries: Annotated[Optional[int], typer.Option("--hc-retries", help=t("cmd.add.opt_hc_retries"))] = None,
    hc_start_period: Annotated[Optional[str], typer.Option("--hc-start-period", help=t("cmd.add.opt_hc_start_period"))] = None,
    set_params: Annotated[Optional[list[str]], typer.Option("--set", help=t("cmd.add.opt_set"))] = None,
) -> None:
    service = service.lower()
    preset = ALL_PRESETS.get(service)
    if preset is None:
        console.print(t("msg.service_unknown", service=service))
        console.print(t("msg.use_rdt_list"))
        raise typer.Exit(1)

    # Загрузить compose если существует, иначе отложим создание до получения answers
    if file.exists():
        data = load_compose(file)
        existing = get_existing_services(data)
        svc_with_hc = get_services_with_healthcheck(data)
    else:
        data = None
        existing = []
        svc_with_hc = set()

    # Проверить что сервис не добавлен дважды (ключ в services = preset.name)
    svc_key = preset.name
    if svc_key in existing:
        console.print(t("msg.file_exists", file=f"{svc_key} in {file}"))
        raise typer.Exit(1)

    # ── Парсинг --set key=value ──────────────────────────────────────────────
    # Позволяет переопределить любой ответ мастера без интерактивного режима.
    # Пример: --set nginx_upstream=app:8080 --set nginx_server_name=example.com
    set_overrides: dict[str, str] = {}
    for param in (set_params or []):
        if "=" not in param:
            console.print(t("msg.set_invalid_format", param=param))
            raise typer.Exit(1)
        k, v = param.split("=", 1)
        set_overrides[k.strip()] = v.strip()

    # Режим с мастером или без
    has_script_flags = (
        yes or port is not None or volume is not None or depends_on is not None
        or container_name_opt is not None or no_ports or network is not None
        or hc_interval is not None or hc_timeout is not None
        or hc_retries is not None or hc_start_period is not None
    )
    if has_script_flags:
        console.print(t("msg.adding_service_script", name=preset.display_name))
        answers = build_script_answers(
            preset=preset,
            port=port,
            volume=volume,
            depends_on=depends_on or [],
            hardcore=hardcore,
            existing_services=existing,
            container_name=container_name_opt,
            no_ports=no_ports,
            network=network,
            hc_interval=hc_interval,
            hc_timeout=hc_timeout,
            hc_retries=hc_retries,
            hc_start_period=hc_start_period,
        )
    else:
        answers = run_wizard(preset, existing, hardcore=hardcore, services_with_healthcheck=svc_with_hc)

    # Применяем --set поверх ответов мастера/скрипта
    if set_overrides:
        answers.update(set_overrides)
        if set_overrides:
            console.print(t("msg.set_overrides_applied", count=len(set_overrides)))

    # Передаём в стратегию информацию о том, у каких сервисов есть healthcheck
    answers["services_with_healthcheck"] = svc_with_hc

    # ── Единый project root ──────────────────────────────────────────────────
    # Правило: root = директория compose-файла (работает как для default так и для --file)
    project_root = _resolve_project_root(file)
    env_file = project_root / ".env"
    env_example_file = project_root / ".env.example"

    # ── ФАЗА ПЛАНИРОВАНИЯ (ничего не пишем на диск) ──────────────────────────

    # Подготовить compose-данные в памяти
    compose_was_new = data is None
    if compose_was_new:
        console.print(t("msg.compose_not_found_create", file=file))
        net_cfg: dict = {
            "type": answers.get("network_type", "bridge"),
            "name": answers.get("network_name", NETWORK_NAME),
        }
        data = make_base_compose(network_config=net_cfg)

    # Получить значения переменных окружения
    env_values = get_env_values(preset.default_env, hardcore=hardcore or not answers.get("use_default_creds", True))

    # Применить стратегию (в памяти)
    strategy = get_strategy(preset, answers)
    service_def = strategy.build()

    # Вставить сервис в compose (в памяти, без записи на диск)
    net_cfg = {
        "type": answers.get("network_type", "bridge"),
        "name": answers.get("network_name", NETWORK_NAME),
    }
    data = inject_service(data, svc_key, service_def, network_config=net_cfg)

    # Построить scaffold-план (директории) без записи на диск
    scaffold_pipeline: ScaffoldPipeline | None = None
    scaffold_plans: list[ScaffoldPlan] = []
    if preset.scaffolds:
        scaffold_pipeline = ScaffoldPipeline(preset.scaffolds, project_root)
        scaffold_plans = scaffold_pipeline.plan()

    # Построить артефакт-план без записи на диск
    pipeline: ArtifactPipeline | None = None
    artifact_plans: list[ArtifactPlan] = []
    if preset.artifacts:
        artifact_ctx = ArtifactContext(
            service_name=svc_key,
            answers=answers,
            env_values=env_values,
            project_root=project_root,
            compose_file=file.resolve(),
            preset=preset,
            smart_env=answers.get("smart_env", {}),
            depends_on=answers.get("depends_on", []),
            parent_service=answers.get("parent_service"),
            service_def=service_def,
        )
        pipeline = ArtifactPipeline(preset.artifacts, artifact_ctx)

        # Preflight-проверка до фактической записи
        issues = pipeline.preflight()
        if issues:
            console.print()
            console.print(t("artifacts.preflight.header"))
            for issue in issues:
                console.print(t("artifacts.preflight.issue", path=issue.artifact_path, reason=issue.reason))
            raise typer.Exit(1)

        artifact_plans = pipeline.plan()

    # Вывести сводку запланированных изменений
    _print_plan_summary(
        file=file,
        svc_key=svc_key,
        env_file=env_file,
        env_values=env_values,
        artifact_plans=artifact_plans,
        compose_file_existed=not compose_was_new,
        scaffold_plans=scaffold_plans,
    )

    # ── ФАЗА ПРИМЕНЕНИЯ (запись на диск) ─────────────────────────────────────

    save_compose(file, data)
    write_env(env_file, env_values)
    write_env_example(env_example_file, env_values)

    console.print(t("msg.service_added", name=preset.display_name, file=file))
    if env_values:
        console.print(t("msg.env_written", file=env_file))

    if scaffold_pipeline is not None:
        scaffold_results = scaffold_pipeline.apply(scaffold_plans)
        ScaffoldPipeline.print_results(scaffold_results, console)

    if pipeline is not None:
        results = pipeline.apply(artifact_plans)
        ArtifactPipeline.print_results(results, console)

        # Фатальная ошибка если хотя бы один артефакт не сгенерирован
        if ArtifactPipeline.has_errors(results):
            console.print(t("artifacts.fatal_error"))
            raise typer.Exit(1)

    # Вывести bootstrap-подсказки после успешного применения
    if preset.bootstrap_hints:
        console.print()
        console.print(t("bootstrap.header"))
        for hint in preset.bootstrap_hints:
            console.print(t("bootstrap.hint", message=hint.message))
            if hint.command:
                console.print(t("bootstrap.command", command=hint.command))


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
# rdt check
# ─────────────────────────────────────────────────────────────────────────────
@app.command(help=t("cmd.check.help"))
def check(
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.check.opt_file"))] = COMPOSE_FILE,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help=t("cmd.check.opt_verbose"))] = False,
) -> None:
    if not file.exists():
        console.print(t("msg.compose_not_found_run", file=file))
        raise typer.Exit(1)

    cmd = ["docker", "compose", "-f", str(file), "config"]
    console.print(t("msg.check_running", file=file))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        if verbose and result.stdout:
            console.print(result.stdout.strip())
        console.print(t("msg.check_ok", file=file))
    else:
        if result.stderr:
            console.print(result.stderr.strip())
        console.print(t("msg.check_fail", file=file))
        raise typer.Exit(result.returncode)


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

