"""
Интерактивный мастер добавления сервиса (Wizard Mode).
"""
from __future__ import annotations
from typing import Any, Callable

import questionary
from rich.console import Console
from rich.panel import Panel

from rdt.presets.catalog import ServicePreset, CATEGORY_RELATIONAL, CATEGORY_NOSQL
from rdt.port_utils import is_port_free, validate_port
from rdt.smart_mapping import get_candidate_parents, apply_smart_mapping
from rdt.strategies.base import NETWORK_NAME
from rdt.strategies.web_server import (
    DEFAULT_CONFIG_DIR, DEFAULT_HTML_DIR, _HTML_MODES,
    DEFAULT_APACHE_CONFIG_DIR, DEFAULT_APACHE_HTML_DIR, DEFAULT_APACHE_SRC_DIR,
)
from rdt.i18n import t

console = Console()

_VOLUME_TYPES = {
    CATEGORY_RELATIONAL: True,
    CATEGORY_NOSQL: True,
}


def run_wizard(
    preset: ServicePreset,
    existing_services: list[str],
    hardcore: bool = False,
    services_with_healthcheck: set[str] | None = None,
) -> dict[str, Any]:
    """
    Запустить интерактивный мастер для выбранного пресета.
    Возвращает словарь answers для передачи в стратегию.
    """
    answers: dict[str, Any] = {}
    _svc_with_hc = services_with_healthcheck or set()

    console.print(t("wizard.configuring", name=preset.display_name))

    # ── 1. Порт ──────────────────────────────────────────────────────────────
    answers["port"] = _ask_port(preset)

    # ── 2. Container name ────────────────────────────────────────────────────
    answers["container_name"] = _ask_container_name(preset)

    # ── 3. Credentials ───────────────────────────────────────────────────────
    if preset.default_env and not hardcore:
        use_default = questionary.confirm(
            t("wizard.use_default_creds"),
            default=True,
        ).ask()
        answers["use_default_creds"] = use_default
    else:
        answers["use_default_creds"] = not hardcore

    # ── 4. Volumes (только для БД) ────────────────────────────────────────────
    if preset.volumes and _needs_volume(preset):
        answers["volume_source"] = _ask_volume(preset)

    # ── 5. Сеть ──────────────────────────────────────────────────────────────
    net_type, net_name = _ask_network()
    answers["network_type"] = net_type
    answers["network_name"] = net_name

    # ── 6. Прокидывание портов (не для host/none) ─────────────────────────────
    if net_type not in ("host", "none"):
        answers["expose_ports"] = _ask_expose_ports()
    else:
        answers["expose_ports"] = False

    # ── 7. Healthcheck параметры ──────────────────────────────────────────────
    if preset.healthcheck:
        answers["healthcheck_params"] = _ask_healthcheck_params(preset)

    # ── 8. depends_on ────────────────────────────────────────────────────────
    if existing_services:
        answers["depends_on"] = _ask_depends_on(existing_services, _svc_with_hc)
    else:
        answers["depends_on"] = []

    # ── 9. Smart Mapping ─────────────────────────────────────────────────────
    candidates = get_candidate_parents(preset.name, existing_services)
    if candidates:
        answers = _ask_smart_mapping(preset.name, candidates, existing_services, answers)

    # ── 10. Service-specific inputs (например, для nginx) ────────────────────
    extra_fn = _SERVICE_EXTRA_WIZARDS.get(preset.name)
    if extra_fn:
        answers = extra_fn(answers)

    return answers


def _ask_port(preset: ServicePreset) -> int:
    default_free = is_port_free(preset.default_port)
    busy_suffix = "" if default_free else t("wizard.port_busy_suffix")
    default_label = f"{preset.default_port}{busy_suffix}"

    choice = questionary.select(
        t("wizard.port_question"),
        choices=[
            questionary.Choice(t("wizard.port_default", label=default_label), value="default"),
            questionary.Choice(t("wizard.port_custom"), value="custom"),
        ],
    ).ask()

    if choice == "default":
        if not default_free:
            console.print(t("wizard.port_busy_warn", port=preset.default_port))
            return _ask_custom_port(preset.default_port)
        return preset.default_port
    else:
        return _ask_custom_port(preset.default_port)


def _ask_custom_port(hint: int) -> int:
    while True:
        raw = questionary.text(t("wizard.port_enter", hint=hint)).ask()
        ok, msg = validate_port(raw or "")
        if ok:
            return int(raw)
        console.print(f"[red]✗ {msg}[/]")


def _ask_container_name(preset: ServicePreset) -> str:
    default_name = preset.name
    choice = questionary.select(
        t("wizard.container_name_question"),
        choices=[
            questionary.Choice(t("wizard.container_name_default", name=default_name), value="default"),
            questionary.Choice(t("wizard.container_name_custom"), value="custom"),
        ],
    ).ask()
    if choice == "default":
        return default_name
    name = questionary.text(t("wizard.container_name_enter")).ask()
    return name.strip() if name and name.strip() else default_name


def _ask_network() -> tuple[str, str]:
    choice = questionary.select(
        t("wizard.network_question"),
        choices=[
            questionary.Choice(t("wizard.network_bridge"), value="bridge"),
            questionary.Choice(t("wizard.network_external"), value="external"),
            questionary.Choice(t("wizard.network_host"), value="host"),
            questionary.Choice(t("wizard.network_none"), value="none"),
        ],
    ).ask()
    if choice == "external":
        name = questionary.text(t("wizard.network_external_name")).ask()
        return "external", (name.strip() if name and name.strip() else "my-network")
    if choice == "bridge":
        return "bridge", NETWORK_NAME
    return choice, ""


def _ask_expose_ports() -> bool:
    return bool(questionary.confirm(
        t("wizard.ports_question"),
        default=True,
    ).ask())


def _ask_healthcheck_params(preset: ServicePreset) -> dict:
    use_default = questionary.confirm(
        t("wizard.healthcheck_question"),
        default=True,
    ).ask()
    if use_default:
        return {}

    hc = preset.healthcheck or {}
    params: dict[str, Any] = {}

    interval = questionary.text(
        t("wizard.healthcheck_interval"),
        default=str(hc.get("interval", "10s")),
    ).ask()
    if interval and interval.strip():
        params["interval"] = interval.strip()

    timeout = questionary.text(
        t("wizard.healthcheck_timeout"),
        default=str(hc.get("timeout", "5s")),
    ).ask()
    if timeout and timeout.strip():
        params["timeout"] = timeout.strip()

    retries_raw = questionary.text(
        t("wizard.healthcheck_retries"),
        default=str(hc.get("retries", 5)),
    ).ask()
    if retries_raw and retries_raw.strip():
        try:
            params["retries"] = int(retries_raw.strip())
        except ValueError:
            pass

    if "start_period" in hc:
        sp = questionary.text(
            t("wizard.healthcheck_start_period"),
            default=str(hc.get("start_period", "30s")),
        ).ask()
        if sp and sp.strip():
            params["start_period"] = sp.strip()

    return params


def _needs_volume(preset: ServicePreset) -> bool:
    return bool(preset.volumes)


def _ask_volume(preset: ServicePreset) -> str:
    default_named = f"{preset.name}_data"
    choice = questionary.select(
        t("wizard.volume_question"),
        choices=[
            questionary.Choice(t("wizard.volume_named", name=default_named), value="named"),
            questionary.Choice(t("wizard.volume_local"), value="local"),
            questionary.Choice(t("wizard.volume_custom"), value="custom"),
        ],
    ).ask()

    if choice == "named":
        return default_named
    elif choice == "local":
        return f"./data/{preset.name}"
    else:
        return questionary.text(t("wizard.volume_enter")).ask() or default_named


def _ask_depends_on(existing_services: list[str], services_with_healthcheck: set[str] | None = None) -> list[str]:
    if not existing_services:
        return []
    svc_with_hc = services_with_healthcheck or set()
    choices = [
        questionary.Choice(
            title=f"{svc}  [healthcheck ✓]" if svc in svc_with_hc else svc,
            value=svc,
        )
        for svc in existing_services
    ]
    selected = questionary.checkbox(
        t("wizard.depends_question"),
        choices=choices,
    ).ask()
    return selected or []


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
        "logstash": "Elasticsearch / OpenSearch",
    }
    parent_label = labels.get(service_name, t("wizard.smart_mapping_default_label"))

    console.print(t("wizard.smart_mapping_found", label=parent_label))

    if len(candidates) == 1:
        use = questionary.confirm(
            t("wizard.smart_mapping_auto", service=candidates[0]),
            default=True,
        ).ask()
        if use:
            answers["parent_service"] = candidates[0]
            answers = apply_smart_mapping(service_name, existing_services, answers)
    else:
        skip_label = t("wizard.smart_mapping_skip")
        selected = questionary.select(
            t("wizard.smart_mapping_select", label=parent_label),
            choices=candidates + [skip_label],
        ).ask()
        if selected != skip_label:
            answers["parent_service"] = selected
            answers = apply_smart_mapping(service_name, existing_services, answers)

    return answers


# ─────────────────────────────────────────────────────────────────────────────
# Service-specific wizard inputs
# ─────────────────────────────────────────────────────────────────────────────

def _ask_nginx_proxy_inputs(answers: dict[str, Any]) -> dict[str, Any]:
    """Дополнительные вопросы для nginx-proxy."""
    console.print(t("wizard.nginx_specific_header"))

    upstream = questionary.text(
        t("wizard.nginx_upstream"),
        default="app:8000",
    ).ask()
    answers["nginx_upstream"] = (upstream or "app:8000").strip()

    server_name = questionary.text(
        t("wizard.nginx_server_name"),
        default="localhost",
    ).ask()
    answers["nginx_server_name"] = (server_name or "localhost").strip()

    config_dir = questionary.text(
        t("wizard.nginx_config_dir"),
        default=DEFAULT_CONFIG_DIR,
    ).ask()
    answers["nginx_config_dir"] = (config_dir or DEFAULT_CONFIG_DIR).strip()

    return answers


def _ask_nginx_html_inputs(answers: dict[str, Any]) -> dict[str, Any]:
    """Дополнительные вопросы для nginx-static и nginx-spa."""
    console.print(t("wizard.nginx_specific_header"))

    server_name = questionary.text(
        t("wizard.nginx_server_name"),
        default="localhost",
    ).ask()
    answers["nginx_server_name"] = (server_name or "localhost").strip()

    config_dir = questionary.text(
        t("wizard.nginx_config_dir"),
        default=DEFAULT_CONFIG_DIR,
    ).ask()
    answers["nginx_config_dir"] = (config_dir or DEFAULT_CONFIG_DIR).strip()

    html_dir = questionary.text(
        t("wizard.nginx_html_dir"),
        default=DEFAULT_HTML_DIR,
    ).ask()
    answers["nginx_html_dir"] = (html_dir or DEFAULT_HTML_DIR).strip()

    return answers


def _ask_apache_static_inputs(answers: dict[str, Any]) -> dict[str, Any]:
    """Дополнительные вопросы для apache-static."""
    console.print(t("wizard.apache_specific_header"))

    server_name = questionary.text(
        t("wizard.apache_server_name"),
        default="localhost",
    ).ask()
    answers["apache_server_name"] = (server_name or "localhost").strip()

    config_dir = questionary.text(
        t("wizard.apache_config_dir"),
        default=DEFAULT_APACHE_CONFIG_DIR,
    ).ask()
    answers["apache_config_dir"] = (config_dir or DEFAULT_APACHE_CONFIG_DIR).strip()

    html_dir = questionary.text(
        t("wizard.apache_html_dir"),
        default=DEFAULT_APACHE_HTML_DIR,
    ).ask()
    answers["apache_html_dir"] = (html_dir or DEFAULT_APACHE_HTML_DIR).strip()

    return answers


def _ask_apache_php_inputs(answers: dict[str, Any]) -> dict[str, Any]:
    """Дополнительные вопросы для apache-php."""
    console.print(t("wizard.apache_specific_header"))

    server_name = questionary.text(
        t("wizard.apache_server_name"),
        default="localhost",
    ).ask()
    answers["apache_server_name"] = (server_name or "localhost").strip()

    config_dir = questionary.text(
        t("wizard.apache_config_dir"),
        default=DEFAULT_APACHE_CONFIG_DIR,
    ).ask()
    answers["apache_config_dir"] = (config_dir or DEFAULT_APACHE_CONFIG_DIR).strip()

    src_dir = questionary.text(
        t("wizard.apache_src_dir"),
        default=DEFAULT_APACHE_SRC_DIR,
    ).ask()
    answers["apache_src_dir"] = (src_dir or DEFAULT_APACHE_SRC_DIR).strip()

    return answers


def _ask_logstash_inputs(answers: dict[str, Any]) -> dict[str, Any]:
    """Дополнительные вопросы для Logstash: режим pipeline."""
    console.print(t("wizard.logstash_specific_header"))

    # Если smart mapping уже задал режим — предложить его как default
    current_mode = answers.get("logstash_pipeline", "beats-stdout")

    mode = questionary.select(
        t("wizard.logstash_pipeline_mode"),
        choices=[
            questionary.Choice(t("wizard.logstash_pipeline_stdout"), value="beats-stdout"),
            questionary.Choice(t("wizard.logstash_pipeline_es"), value="beats-es"),
        ],
        default="beats-stdout" if current_mode == "beats-stdout" else "beats-es",
    ).ask()

    answers["logstash_pipeline"] = mode or "beats-stdout"

    if answers["logstash_pipeline"] == "beats-es":
        default_host = answers.get("logstash_es_host") or \
                       (answers.get("smart_env") or {}).get("LOGSTASH_ES_HOST") or \
                       "elasticsearch:9200"
        es_host = questionary.text(
            t("wizard.logstash_es_host"),
            default=default_host,
        ).ask()
        answers["logstash_es_host"] = (es_host or default_host).strip()

    # Установить condition-флаги
    answers["logstash_pipeline_stdout"] = (answers["logstash_pipeline"] == "beats-stdout")
    answers["logstash_pipeline_es"] = (answers["logstash_pipeline"] == "beats-es")

    return answers


#: Маппинг service_name → callable для service-specific wizard вопросов.
#: Расширяйте этот словарь при добавлении новых сервисов с конфигами.
_SERVICE_EXTRA_WIZARDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "nginx-proxy":   _ask_nginx_proxy_inputs,
    "nginx-static":  _ask_nginx_html_inputs,
    "nginx-spa":     _ask_nginx_html_inputs,
    "apache-static": _ask_apache_static_inputs,
    "apache-php":    _ask_apache_php_inputs,
    "logstash":      _ask_logstash_inputs,
}


# ─────────────────────────────────────────────────────────────────────────────
# Главное интерактивное меню (запускается при rdt без аргументов)
# ─────────────────────────────────────────────────────────────────────────────

def run_main_menu() -> str:
    """
    Показать главное интерактивное меню.
    Возвращает строку-ключ выбранного действия.
    """
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]{t('menu.panel_title')}[/]\n"
        f"[dim]{t('menu.panel_subtitle')}[/]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    choice = questionary.select(
        t("menu.question"),
        choices=[
            questionary.Choice(t("menu.add"),   value="add"),
            questionary.Choice(t("menu.init"),  value="init"),
            questionary.Choice(t("menu.list"),  value="list"),
            questionary.Choice(t("menu.up"),    value="up"),
            questionary.Choice(t("menu.check"), value="check"),
            questionary.Choice(t("menu.lang"),  value="lang"),
            questionary.Choice(t("menu.help"),  value="help"),
            questionary.Choice(t("menu.exit"),  value="exit"),
        ],
        use_indicator=True,
    ).ask()

    return choice or "exit"


def ask_service_choice() -> str | None:
    """
    Показать каталог сервисов по категориям и вернуть выбранное имя сервиса
    (или None если пользователь выбрал «Назад»).
    """
    from rdt.presets.catalog import ALL_PRESETS

    categories: dict[str, list[ServicePreset]] = {}
    for preset in ALL_PRESETS.values():
        categories.setdefault(preset.category, []).append(preset)

    choices: list = []
    for category, presets in categories.items():
        choices.append(questionary.Separator(f"── {category} ──"))
        for p in presets:
            choices.append(questionary.Choice(
                f"{p.display_name}  ({t('menu.port_label')} {p.default_port})",
                value=p.name,
            ))

    choices.append(questionary.Separator("─" * 36))
    choices.append(questionary.Choice(t("menu.back"), value=None))

    selected = questionary.select(
        t("menu.service_choice"),
        choices=choices,
    ).ask()

    return selected


def build_script_answers(
    preset: ServicePreset,
    port: int | None,
    volume: str | None,
    depends_on: list[str],
    hardcore: bool,
    existing_services: list[str],
    container_name: str | None = None,
    no_ports: bool = False,
    network: str | None = None,
    hc_interval: str | None = None,
    hc_timeout: str | None = None,
    hc_retries: int | None = None,
    hc_start_period: str | None = None,
) -> dict[str, Any]:
    """
    Сформировать словарь answers из CLI-флагов без интерактивного мастера.
    Используется при запуске rdt add <service> --yes [--port X] [--volume Y] ...
    """
    answers: dict[str, Any] = {}

    # Порт
    answers["port"] = port if port is not None else preset.default_port

    # Container name
    answers["container_name"] = container_name if container_name else preset.name

    # Credentials
    answers["use_default_creds"] = not hardcore

    # Volume (только для сервисов с volumes)
    if preset.volumes:
        answers["volume_source"] = volume if volume is not None else f"{preset.name}_data"

    # Сеть
    if network is None or network == "bridge":
        answers["network_type"] = "bridge"
        answers["network_name"] = NETWORK_NAME
    elif network == "host":
        answers["network_type"] = "host"
        answers["network_name"] = ""
    elif network == "none":
        answers["network_type"] = "none"
        answers["network_name"] = ""
    else:
        # Имя external-сети
        answers["network_type"] = "external"
        answers["network_name"] = network

    # Прокидывание портов
    answers["expose_ports"] = not no_ports

    # Healthcheck параметры
    hc_params: dict[str, Any] = {}
    if hc_interval:
        hc_params["interval"] = hc_interval
    if hc_timeout:
        hc_params["timeout"] = hc_timeout
    if hc_retries is not None:
        hc_params["retries"] = hc_retries
    if hc_start_period:
        hc_params["start_period"] = hc_start_period
    answers["healthcheck_params"] = hc_params

    # Зависимости
    answers["depends_on"] = list(depends_on)

    # Auto Smart Mapping — автоматически применяем первого найденного кандидата
    candidates = get_candidate_parents(preset.name, existing_services)
    if candidates:
        answers["parent_service"] = candidates[0]
        answers = apply_smart_mapping(preset.name, existing_services, answers)

    # Service-specific defaults для script mode
    _apply_service_script_defaults(preset, answers)

    return answers


def _apply_service_script_defaults(preset: ServicePreset, answers: dict[str, Any]) -> None:
    """
    Установить service-specific значения по умолчанию для script mode.
    Вызывается из build_script_answers после всех общих параметров.
    """
    if preset.name == "nginx-proxy":
        answers.setdefault("nginx_upstream", "app:8000")
        answers.setdefault("nginx_server_name", "localhost")
        answers.setdefault("nginx_config_dir", DEFAULT_CONFIG_DIR)

    elif preset.name in _HTML_MODES:
        answers.setdefault("nginx_server_name", "localhost")
        answers.setdefault("nginx_config_dir", DEFAULT_CONFIG_DIR)
        answers.setdefault("nginx_html_dir", DEFAULT_HTML_DIR)

    elif preset.name == "apache-static":
        answers.setdefault("apache_server_name", "localhost")
        answers.setdefault("apache_config_dir", DEFAULT_APACHE_CONFIG_DIR)
        answers.setdefault("apache_html_dir", DEFAULT_APACHE_HTML_DIR)

    elif preset.name == "apache-php":
        answers.setdefault("apache_server_name", "localhost")
        answers.setdefault("apache_config_dir", DEFAULT_APACHE_CONFIG_DIR)
        answers.setdefault("apache_src_dir", DEFAULT_APACHE_SRC_DIR)

    elif preset.name == "logstash":
        # Режим pipeline: если smart mapping нашёл ES — beats-es, иначе beats-stdout
        pipeline = answers.get("logstash_pipeline", "beats-stdout")
        answers["logstash_pipeline"] = pipeline
        answers["logstash_pipeline_stdout"] = (pipeline == "beats-stdout")
        answers["logstash_pipeline_es"] = (pipeline == "beats-es")
        if pipeline == "beats-es":
            answers.setdefault(
                "logstash_es_host",
                (answers.get("smart_env") or {}).get("LOGSTASH_ES_HOST", "elasticsearch:9200"),
            )

