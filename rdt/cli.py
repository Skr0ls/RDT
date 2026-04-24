"""
CLI entry point for RDT (Rambo Docker Tools).
Commands: init, add, list, up, check, doctor, lang

Responsibilities: argument parsing, interactive wizard, and Rich output.
All business logic is delegated to rdt.core.
"""
from __future__ import annotations
from pathlib import Path
from typing import Annotated, Any, Optional

import questionary
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from rdt.presets.catalog import ALL_PRESETS, ServicePreset
from rdt.yaml_manager import (
    load_compose,
    get_existing_services,
    get_services_with_healthcheck,
    DEFAULT_COMPOSE_FILE,
    resolve_default_compose_file,
)
from rdt.wizard import run_wizard, run_main_menu, ask_service_choice
from rdt.i18n import t
import rdt.i18n as i18n
from rdt.core import (
    RdtError,
    init as core_init,
    add as core_add,
    add_from_answers,
    remove as core_remove,
    list_presets as core_list_presets,
    doctor as core_doctor,
    check as core_check,
    up as core_up,
)

app = typer.Typer(
    name="rdt",
    help=t("app.help"),
    rich_markup_mode="rich",
)
console = Console()

COMPOSE_FILE = Path(DEFAULT_COMPOSE_FILE)


def _resolve_project_root(file: Path) -> Path:
    return file.parent.resolve()


def _resolve_cli_compose_file(file: Path) -> Path:
    """Prefer an existing common Compose filename when the default path is used."""
    return resolve_default_compose_file(file) if file == COMPOSE_FILE else file


# ─────────────────────────────────────────────────────────────────────────────
# Callback — starts the interactive menu when rdt is run without arguments
# ─────────────────────────────────────────────────────────────────────────────
@app.callback(invoke_without_command=True, help=t("app.callback_help"))
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _run_interactive(ctx)


def _run_interactive(ctx: typer.Context) -> None:
    """Start the main interactive menu."""
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
            continue  # The menu is redrawn immediately with the new language.

        console.print()
        cont = questionary.confirm(t("msg.do_more"), default=False).ask()
        if not cont:
            break


def _show_help(ctx: typer.Context) -> None:
    """Print the full RDT command help, equivalent to rdt --help."""
    console.print(ctx.get_help())


def _change_language() -> None:
    """Interactively change the language inside the current session."""
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
    file = _resolve_cli_compose_file(file)
    try:
        result = core_init(file, force=force)
    except RdtError as e:
        console.print(str(e))
        raise typer.Exit(1)

    console.print(t("msg.compose_created", file=result.file))
    for path in result.created[1:]:
        console.print(t("msg.env_created", file=path))


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
    file = _resolve_cli_compose_file(file)
    service = service.lower()
    preset = ALL_PRESETS.get(service)
    if preset is None:
        console.print(t("msg.service_unknown", service=service))
        console.print(t("msg.use_rdt_list"))
        raise typer.Exit(1)

    # Parse --set key=value.
    set_overrides: dict[str, str] = {}
    for param in (set_params or []):
        if "=" not in param:
            console.print(t("msg.set_invalid_format", param=param))
            raise typer.Exit(1)
        k, v = param.split("=", 1)
        set_overrides[k.strip()] = v.strip()

    has_script_flags = (
        yes or port is not None or volume is not None or depends_on is not None
        or container_name_opt is not None or no_ports or network is not None
        or hc_interval is not None or hc_timeout is not None
        or hc_retries is not None or hc_start_period is not None
    )

    try:
        if has_script_flags:
            console.print(t("msg.adding_service_script", name=preset.display_name))
            result = core_add(
                service=service,
                file=file,
                port=port,
                volume=volume,
                depends_on=depends_on,
                hardcore=hardcore,
                no_ports=no_ports,
                network=network,
                container_name=container_name_opt,
                hc_interval=hc_interval,
                hc_timeout=hc_timeout,
                hc_retries=hc_retries,
                hc_start_period=hc_start_period,
                set_vars=set_overrides or None,
            )
        else:
            # Wizard mode remains interactive in the CLI.
            if file.exists():
                data = load_compose(file)
                existing = get_existing_services(data)
                svc_with_hc = get_services_with_healthcheck(data)
            else:
                existing = []
                svc_with_hc = set()
            answers: dict[str, Any] = run_wizard(
                preset, existing, hardcore=hardcore, services_with_healthcheck=svc_with_hc,
            )
            if set_overrides:
                answers.update(set_overrides)
                console.print(t("msg.set_overrides_applied", count=len(set_overrides)))
            answers["services_with_healthcheck"] = svc_with_hc
            result = add_from_answers(service, answers, file, hardcore=hardcore)
    except RdtError as e:
        console.print(str(e))
        raise typer.Exit(1)

    # ── Presentation ──────────────────────────────────────────────────────────
    project_root = _resolve_project_root(file)
    env_file = project_root / ".env"

    console.print(t("msg.service_added", name=preset.display_name, file=file))
    if result.env_vars:
        console.print(t("msg.env_written", file=env_file))
    for path in result.artifacts_created:
        console.print(t("plan.artifact_create", path=path))
    if result.hints:
        console.print()
        console.print(t("bootstrap.header"))
        for hint in result.hints:
            console.print(t("bootstrap.hint", message=hint))


# ─────────────────────────────────────────────────────────────────────────────
# rdt list
# ─────────────────────────────────────────────────────────────────────────────
@app.command(name="list", help=t("cmd.list.help"))
def list_presets() -> None:
    presets = core_list_presets()
    categories: dict[str, list] = {}
    for p in presets:
        categories.setdefault(p.category, []).append(p)

    table = Table(title=t("table.title"), box=box.ROUNDED, show_lines=True)
    table.add_column(t("table.col_category"), style="cyan bold", no_wrap=True)
    table.add_column(t("table.col_command"), style="green")
    table.add_column(t("table.col_service"), style="white")
    table.add_column(t("table.col_image"), style="dim")
    table.add_column(t("table.col_port"), style="yellow", justify="right")

    for category, items in categories.items():
        for i, p in enumerate(items):
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
    file = _resolve_cli_compose_file(file)
    try:
        result = core_up(file, detach=detach)
    except RdtError as e:
        console.print(str(e))
        raise typer.Exit(1)
    console.print(t("msg.running_cmd", cmd=result.command))
    raise typer.Exit(result.returncode)


# ─────────────────────────────────────────────────────────────────────────────
# rdt check
# ─────────────────────────────────────────────────────────────────────────────
@app.command(help=t("cmd.check.help"))
def check(
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.check.opt_file"))] = COMPOSE_FILE,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help=t("cmd.check.opt_verbose"))] = False,
) -> None:
    file = _resolve_cli_compose_file(file)
    console.print(t("msg.check_running", file=file))
    try:
        result = core_check(file)
    except RdtError as e:
        console.print(str(e))
        raise typer.Exit(1)

    if result.valid:
        console.print(t("msg.check_ok", file=file))
    else:
        if result.error:
            console.print(result.error)
        console.print(t("msg.check_fail", file=file))
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# rdt remove
# ─────────────────────────────────────────────────────────────────────────────

@app.command(name="remove", help=t("cmd.remove.help"))
def remove(
    service: Annotated[Optional[str], typer.Argument(help=t("cmd.remove.arg_service"))] = None,
    file: Annotated[Path, typer.Option("--file", "-f", help=t("cmd.remove.opt_file"))] = COMPOSE_FILE,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=t("cmd.remove.opt_yes"))] = False,
    clean_env: Annotated[bool, typer.Option("--clean-env", help=t("cmd.remove.opt_clean_env"))] = False,
    clean_artifacts: Annotated[bool, typer.Option("--clean-artifacts", help=t("cmd.remove.opt_clean_artifacts"))] = False,
) -> None:
    file = _resolve_cli_compose_file(file)
    if not file.exists():
        console.print(t("remove.compose_not_found", file=file))
        raise typer.Exit(1)

    data = load_compose(file)
    existing = get_existing_services(data)

    if not existing:
        console.print(t("remove.no_services", file=file))
        raise typer.Exit(1)

    # ── Service selection (interactive or argument) ──────────────────────────
    if service is None:
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

    # ── Interactive option questions when --yes is not provided ──────────────
    if not yes:
        from rdt.env_manager import find_orphaned_vars
        from rdt.core import _get_artifact_paths
        project_root = _resolve_project_root(file)

        orphaned_vars = find_orphaned_vars(data, service)
        artifact_paths = _get_artifact_paths(service, project_root)

        if orphaned_vars and not clean_env:
            clean_env = questionary.confirm(t("remove.ask_clean_env"), default=True).ask() or False
        if artifact_paths and not clean_artifacts:
            clean_artifacts = questionary.confirm(t("remove.ask_clean_artifacts"), default=False).ask() or False

        confirmed = questionary.confirm(t("remove.confirm"), default=False).ask()
        if not confirmed:
            console.print(t("remove.cancelled"))
            raise typer.Exit(0)

    # ── Apply through core ───────────────────────────────────────────────────
    try:
        result = core_remove(service, file, clean_env=clean_env, clean_artifacts=clean_artifacts)
    except RdtError as e:
        console.print(str(e))
        raise typer.Exit(1)

    # ── Presentation ──────────────────────────────────────────────────────────
    project_root = _resolve_project_root(file)
    env_file = project_root / ".env"

    console.print(t("remove.compose_saved", file=file))
    for vol in result.removed_volumes:
        console.print(t("remove.volume_removed", volume=vol))
    if result.cleaned_env_vars:
        console.print(t("remove.env_file_cleaned", file=env_file, count=len(result.cleaned_env_vars)))
    for p in result.cleaned_files:
        console.print(t("remove.artifact_removed", path=p))
    if result.dependents_warned:
        console.print(t("remove.dependents_warn", service=service))
        for dep in result.dependents_warned:
            console.print(t("remove.dependents_entry", dependent=dep))
    console.print(t("remove.done", service=service))


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
    file = _resolve_cli_compose_file(file)
    console.print(t("doctor.header"))

    try:
        result = core_doctor(file)
    except RdtError as e:
        console.print(str(e))
        raise typer.Exit(1)

    table = Table(box=box.ROUNDED, show_header=True, show_lines=False, expand=False)
    table.add_column("", width=3, no_wrap=True)
    table.add_column("Check", style="bold", no_wrap=True)
    table.add_column("Result")

    for r in result.checks:
        icon = _STATUS_ICON.get(r["status"], "?")
        style = _STATUS_STYLE.get(r["status"], "")
        label = t(_CHECK_LABEL_KEYS.get(r["name"], r["name"]))
        table.add_row(icon, label, f"[{style}]{r['message']}[/]")

    console.print(table)

    for r in result.checks:
        if r.get("details"):
            console.print()
            label = t(_CHECK_LABEL_KEYS.get(r["name"], r["name"]))
            icon = _STATUS_ICON.get(r["status"], "?")
            console.print(f"  {icon} [bold]{label}:[/]")
            for line in r["details"]:
                console.print(line)

    errors = result.summary.get("error", 0)
    warns  = result.summary.get("warn", 0)
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
    # No arguments: choose the language interactively.
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

    # Unknown action.
    console.print(t("lang.unknown", lang=action))
    raise typer.Exit(1)


if __name__ == "__main__":
    app()

