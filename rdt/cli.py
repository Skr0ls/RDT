"""
CLI точка входа для RDT (Rambo Docker Tools).
Команды: init, add, list, up, check, doctor, lang
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import questionary
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from rdt.presets.catalog import ALL_PRESETS, ServicePreset
from rdt.strategies.base import NETWORK_NAME
from rdt.strategies.factory import get_strategy
from rdt.yaml_manager import (
    load_compose, save_compose, make_base_compose, inject_service,
    get_existing_services, get_services_with_healthcheck,
    get_dependents, remove_service, get_service_named_volumes,
)
from rdt.env_manager import (
    get_env_values, write_env, write_env_example,
    find_orphaned_vars, remove_vars_from_env_file,
)
from rdt.wizard import run_wizard, run_main_menu, ask_service_choice, build_script_answers
from rdt.artifacts import (
    ArtifactContext, ArtifactPipeline, ArtifactPlan, ArtifactResult, PreflightIssue,
    ScaffoldPipeline, ScaffoldPlan, ScaffoldResult,
)
from rdt.i18n import t
import rdt.i18n as i18n
from rdt.doctor import run_all_checks, CheckResult

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

        elif action == "doctor":
            doctor()

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

        elif action == "remove":
            try:
                remove()
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


def _do_rollback(
    console: Console,
    compose_file: Path,
    compose_was_new: bool,
    compose_snapshot: str | None,
    env_file: Path,
    env_existed_before: bool,
    env_snapshot: str | None,
    env_example_file: Path,
    env_example_existed_before: bool,
    env_example_snapshot: str | None,
    scaffold_results: list[ScaffoldResult],
    artifact_results: list[ArtifactResult],
) -> None:
    """Best-effort rollback: восстановить compose/env и удалить созданные файлы/директории."""
    console.print(t("rollback.header"))

    # 1. Откатить compose файл
    try:
        if compose_was_new:
            if compose_file.exists():
                compose_file.unlink()
                console.print(t("rollback.compose_removed", file=str(compose_file)))
        elif compose_snapshot is not None:
            compose_file.write_text(compose_snapshot, encoding="utf-8")
            console.print(t("rollback.compose_restored", file=str(compose_file)))
    except Exception as exc:
        console.print(t("rollback.warn", error=str(exc)))

    # 2. Откатить .env
    try:
        if not env_existed_before:
            if env_file.exists():
                env_file.unlink()
                console.print(t("rollback.env_removed", file=str(env_file)))
        elif env_snapshot is not None:
            env_file.write_text(env_snapshot, encoding="utf-8")
            console.print(t("rollback.env_restored", file=str(env_file)))
    except Exception as exc:
        console.print(t("rollback.warn", error=str(exc)))

    # 3. Откатить .env.example
    try:
        if not env_example_existed_before:
            if env_example_file.exists():
                env_example_file.unlink()
                console.print(t("rollback.env_removed", file=str(env_example_file)))
        elif env_example_snapshot is not None:
            env_example_file.write_text(env_example_snapshot, encoding="utf-8")
            console.print(t("rollback.env_restored", file=str(env_example_file)))
    except Exception as exc:
        console.print(t("rollback.warn", error=str(exc)))

    # 4. Удалить созданные артефакты
    for r in artifact_results:
        if r.status == "created":
            try:
                if r.path.exists():
                    r.path.unlink()
                    console.print(t("rollback.artifact_removed", path=str(r.path)))
            except Exception as exc:
                console.print(t("rollback.warn", error=str(exc)))

    # 5. Удалить созданные scaffold-директории (только пустые)
    for r in scaffold_results:
        if r.status == "created":
            try:
                if r.path.exists() and r.path.is_dir() and not any(r.path.iterdir()):
                    r.path.rmdir()
                    console.print(t("rollback.dir_removed", path=str(r.path)))
            except Exception as exc:
                console.print(t("rollback.warn", error=str(exc)))

    console.print(t("rollback.done"))


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

    # ── Снимок состояния перед записью (для best-effort rollback) ────────────
    compose_snapshot: str | None = file.read_text(encoding="utf-8") if file.exists() else None
    env_existed_before = env_file.exists()
    env_snapshot: str | None = env_file.read_text(encoding="utf-8") if env_existed_before else None
    env_example_existed_before = env_example_file.exists()
    env_example_snapshot: str | None = (
        env_example_file.read_text(encoding="utf-8") if env_example_existed_before else None
    )

    # ── ФАЗА ПРИМЕНЕНИЯ (запись на диск) ─────────────────────────────────────

    save_compose(file, data)
    write_env(env_file, env_values)
    write_env_example(env_example_file, env_values)

    console.print(t("msg.service_added", name=preset.display_name, file=file))
    if env_values:
        console.print(t("msg.env_written", file=env_file))

    scaffold_results: list[ScaffoldResult] = []
    if scaffold_pipeline is not None:
        scaffold_results = scaffold_pipeline.apply(scaffold_plans)
        ScaffoldPipeline.print_results(scaffold_results, console)

        # Scaffold errors теперь фатальны + best-effort rollback
        if ScaffoldPipeline.has_errors(scaffold_results):
            console.print(t("scaffold.fatal_error"))
            _do_rollback(
                console=console,
                compose_file=file,
                compose_was_new=compose_was_new,
                compose_snapshot=compose_snapshot,
                env_file=env_file,
                env_existed_before=env_existed_before,
                env_snapshot=env_snapshot,
                env_example_file=env_example_file,
                env_example_existed_before=env_example_existed_before,
                env_example_snapshot=env_example_snapshot,
                scaffold_results=scaffold_results,
                artifact_results=[],
            )
            raise typer.Exit(1)

    if pipeline is not None:
        artifact_results = pipeline.apply(artifact_plans)
        ArtifactPipeline.print_results(artifact_results, console)

        # Фатальная ошибка если хотя бы один артефакт не сгенерирован — выполнить rollback
        if ArtifactPipeline.has_errors(artifact_results):
            console.print(t("artifacts.fatal_error"))
            _do_rollback(
                console=console,
                compose_file=file,
                compose_was_new=compose_was_new,
                compose_snapshot=compose_snapshot,
                env_file=env_file,
                env_existed_before=env_existed_before,
                env_snapshot=env_snapshot,
                env_example_file=env_example_file,
                env_example_existed_before=env_example_existed_before,
                env_example_snapshot=env_example_snapshot,
                scaffold_results=scaffold_results,
                artifact_results=artifact_results,
            )
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
# rdt remove
# ─────────────────────────────────────────────────────────────────────────────

def _get_artifact_paths_for_service(service_name: str, project_root: Path) -> list[Path]:
    """Вернуть список companion-файлов для сервиса, которые существуют на диске.

    Берёт список артефактов из пресета (если он есть) и возвращает
    только те файлы, что физически присутствуют в project_root.
    """
    preset = ALL_PRESETS.get(service_name)
    if preset is None or not preset.artifacts:
        return []
    paths: list[Path] = []
    for artifact_def in preset.artifacts:
        candidate = project_root / artifact_def.relative_path
        if candidate.exists():
            paths.append(candidate)
    return paths


@app.command(name="remove", help=t("cmd.remove.help"))
def remove(
    service: Annotated[Optional[str], typer.Argument(help=t("cmd.remove.arg_service"))] = None,
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.remove.opt_file"))] = COMPOSE_FILE,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=t("cmd.remove.opt_yes"))] = False,
    clean_env: Annotated[bool, typer.Option("--clean-env", help=t("cmd.remove.opt_clean_env"))] = False,
    clean_artifacts: Annotated[bool, typer.Option("--clean-artifacts", help=t("cmd.remove.opt_clean_artifacts"))] = False,
) -> None:
    # ── 1. Проверить существование compose-файла ─────────────────────────────
    if not file.exists():
        console.print(t("remove.compose_not_found", file=file))
        raise typer.Exit(1)

    project_root = _resolve_project_root(file)
    env_file = project_root / ".env"
    env_example_file = project_root / ".env.example"

    data = load_compose(file)
    existing = get_existing_services(data)

    if not existing:
        console.print(t("remove.no_services", file=file))
        raise typer.Exit(1)

    # ── 2. Выбор сервиса (интерактивно или аргумент) ─────────────────────────
    if service is None:
        # Интерактивный выбор
        from rdt.wizard import ask_remove_service_choice
        service = ask_remove_service_choice(existing)
        if not service:
            console.print(t("remove.cancelled"))
            raise typer.Exit(0)
    else:
        service = service.lower()

    if service not in existing:
        console.print(t("remove.service_not_found", service=service, file=file,
                        available=", ".join(existing)))
        raise typer.Exit(1)

    console.print(t("remove.header", service=service))

    # ── 3. Предупреждение о зависимых сервисах ───────────────────────────────
    dependents = get_dependents(data, service)
    if dependents:
        console.print(t("remove.dependents_warn", service=service))
        for dep in dependents:
            console.print(t("remove.dependents_entry", dependent=dep))
        console.print(t("remove.dependents_note"))
        console.print()

    # ── 4. Анализ: orphaned ENV vars ─────────────────────────────────────────
    orphaned_vars: set[str] = set()
    if clean_env or not yes:
        orphaned_vars = find_orphaned_vars(data, service)

    # ── 5. Анализ: companion файлы ───────────────────────────────────────────
    artifact_paths: list[Path] = []
    if clean_artifacts or not yes:
        artifact_paths = _get_artifact_paths_for_service(service, project_root)

    # ── 6. Интерактивные вопросы (если не --yes) ─────────────────────────────
    if not yes:
        if orphaned_vars and not clean_env:
            clean_env = questionary.confirm(
                t("remove.ask_clean_env"),
                default=True,
            ).ask() or False

        if artifact_paths and not clean_artifacts:
            clean_artifacts = questionary.confirm(
                t("remove.ask_clean_artifacts"),
                default=False,
            ).ask() or False

    # ── 7. Показать план ─────────────────────────────────────────────────────
    console.print(t("remove.plan_header"))
    console.print(t("remove.plan_service", service=service, file=file))

    # Named volumes (рассчитать предварительно)
    preview_volumes = _preview_orphaned_volumes(data, service)
    for vol in preview_volumes:
        console.print(t("remove.plan_volume", volume=vol))

    if clean_env and orphaned_vars:
        for var in sorted(orphaned_vars):
            console.print(t("remove.plan_env_var", var=var, file=env_file))
    elif not orphaned_vars:
        console.print(t("remove.plan_env_skip"))
    else:
        console.print(t("remove.plan_env_skip"))

    if clean_artifacts and artifact_paths:
        for p in artifact_paths:
            console.print(t("remove.plan_artifact", path=str(p)))
    else:
        console.print(t("remove.plan_artifact_skip"))

    console.print()

    # ── 8. Финальное подтверждение ───────────────────────────────────────────
    if not yes:
        confirmed = questionary.confirm(t("remove.confirm"), default=False).ask()
        if not confirmed:
            console.print(t("remove.cancelled"))
            raise typer.Exit(0)

    # ── 9. ПРИМЕНЕНИЕ ────────────────────────────────────────────────────────

    # Удалить сервис + orphaned named volumes из compose
    data, removed_volumes = remove_service(data, service)
    save_compose(file, data)
    console.print(t("remove.compose_saved", file=file))
    for vol in removed_volumes:
        console.print(t("remove.volume_removed", volume=vol))

    # Очистить ENV
    if clean_env and orphaned_vars:
        removed_count = remove_vars_from_env_file(env_file, orphaned_vars)
        remove_vars_from_env_file(env_example_file, orphaned_vars)
        if removed_count:
            console.print(t("remove.env_file_cleaned", file=env_file, count=removed_count))

    # Удалить companion-файлы
    if clean_artifacts and artifact_paths:
        for p in artifact_paths:
            try:
                if p.exists():
                    if p.is_file():
                        p.unlink()
                    else:
                        import shutil
                        shutil.rmtree(p)
                    console.print(t("remove.artifact_removed", path=str(p)))
                else:
                    console.print(t("remove.artifact_not_found", path=str(p)))
            except Exception as exc:
                console.print(t("remove.artifact_error", path=str(p), error=str(exc)))

    console.print(t("remove.done", service=service))


def _preview_orphaned_volumes(data: Any, service_name: str) -> list[str]:
    """Список named volumes, которые станут осиротевшими после удаления сервиса."""
    service_volumes = get_service_named_volumes(data, service_name)
    still_used: set[str] = set()
    for svc_name, svc_def in (data.get("services") or {}).items():
        if svc_name == service_name:
            continue
        for vol in (svc_def or {}).get("volumes", []):
            vol_str = str(vol)
            if ":" in vol_str:
                source = vol_str.split(":")[0]
                if not source.startswith(".") and not source.startswith("/"):
                    still_used.add(source)
    return [v for v in service_volumes if v not in still_used]


# ─────────────────────────────────────────────────────────────────────────────
# rdt doctor
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_ICON = {
    "ok":    "[green]✓[/]",
    "warn":  "[yellow]⚠[/]",
    "error": "[red]✗[/]",
    "skip":  "[dim]─[/]",
}
_STATUS_STYLE = {
    "ok":    "green",
    "warn":  "yellow",
    "error": "red",
    "skip":  "dim",
}
_CHECK_LABEL_KEYS = {
    "docker":           "doctor.check_docker",
    "compose":          "doctor.check_compose",
    "compose_valid":    "doctor.check_compose_valid",
    "env_vars":         "doctor.check_env_vars",
    "port_conflicts":   "doctor.check_port_conflicts",
    "dangling_deps":    "doctor.check_dangling_deps",
    "companion_files":  "doctor.check_companion_files",
}


@app.command(name="doctor", help=t("cmd.doctor.help"))
def doctor(
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.doctor.opt_file"))] = COMPOSE_FILE,
) -> None:
    from rich.table import Table
    from rich import box as rich_box

    project_root = _resolve_project_root(file)
    console.print(t("doctor.header"))

    results = run_all_checks(file, project_root)

    table = Table(box=rich_box.ROUNDED, show_header=True, show_lines=False, expand=False)
    table.add_column("", width=3, no_wrap=True)
    table.add_column(t("doctor.check_docker").split()[0] if False else "Check", style="bold", no_wrap=True)
    table.add_column("Result")

    for r in results:
        icon = _STATUS_ICON.get(r.status, "?")
        style = _STATUS_STYLE.get(r.status, "")
        label = t(_CHECK_LABEL_KEYS.get(r.name, r.name))
        table.add_row(icon, label, f"[{style}]{r.message}[/]")

    console.print(table)

    # Подробности (details) — отдельно под таблицей
    for r in results:
        if r.details:
            console.print()
            label = t(_CHECK_LABEL_KEYS.get(r.name, r.name))
            icon = _STATUS_ICON.get(r.status, "?")
            console.print(f"  {icon} [bold]{label}:[/]")
            for line in r.details:
                console.print(line)

    # Итоговая строка
    errors = sum(1 for r in results if r.status == "error")
    warns  = sum(1 for r in results if r.status == "warn")

    console.print()
    if errors == 0 and warns == 0:
        console.print(t("doctor.summary_ok"))
    elif errors == 0:
        console.print(t("doctor.summary_warn", warn=warns))
    else:
        console.print(t("doctor.summary_error", error=errors, warn=warns))

    if errors:
        raise typer.Exit(1)


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

