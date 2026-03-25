"""
Smart Mapping — автоматическое предложение связей между сервисами.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import CONTAINER_PREFIX

# Описание умных связок: {service_name: handler_func}
# handler получает (existing_services: list[str], answers: dict) → обновляет answers["smart_env"]


def apply_smart_mapping(
    service_name: str,
    existing_services: list[str],
    answers: dict[str, Any],
) -> dict[str, Any]:
    """
    Применяет Smart Mapping для service_name.
    Возвращает обновлённый словарь answers.
    """
    handlers = {
        "pgadmin": _pgadmin_mapping,
        "kafka-ui": _kafka_ui_mapping,
        "grafana": _grafana_mapping,
        "phpmyadmin": _phpmyadmin_mapping,
        "mongo-express": _mongo_express_mapping,
    }
    handler = handlers.get(service_name)
    if handler:
        handler(existing_services, answers)
    return answers


def _pgadmin_mapping(existing: list[str], answers: dict) -> None:
    """pgAdmin → Postgres: заполнить сервер БД."""
    pg_services = [s for s in existing if "postgres" in s]
    if pg_services:
        selected = answers.get("parent_service", pg_services[0])
        answers.setdefault("smart_env", {})
        answers["smart_env"].update({
            "PGADMIN_DEFAULT_SERVER": selected,
        })
        # depends_on
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps


def _kafka_ui_mapping(existing: list[str], answers: dict) -> None:
    """Kafka-UI → Kafka: KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS."""
    kafka_services = [s for s in existing if "kafka" in s and "ui" not in s]
    if kafka_services:
        selected = answers.get("parent_service", kafka_services[0])
        bootstrap = f"{CONTAINER_PREFIX}kafka:9092"
        answers.setdefault("smart_env", {})
        answers["smart_env"]["KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS"] = bootstrap
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps


def _grafana_mapping(existing: list[str], answers: dict) -> None:
    """Grafana → Prometheus: DataSource URL."""
    prom_services = [s for s in existing if "prometheus" in s]
    if prom_services:
        selected = answers.get("parent_service", prom_services[0])
        answers.setdefault("smart_env", {})
        answers["smart_env"].update({
            "GF_DATASOURCES_DEFAULT_TYPE": "prometheus",
            "GF_DATASOURCES_DEFAULT_URL": f"http://{CONTAINER_PREFIX}prometheus:9090",
            "GF_DATASOURCES_DEFAULT_ACCESS": "proxy",
        })
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps


def _phpmyadmin_mapping(existing: list[str], answers: dict) -> None:
    """phpMyAdmin → MySQL/MariaDB: PMA_HOST."""
    mysql_services = [s for s in existing if "mysql" in s or "mariadb" in s]
    if mysql_services:
        selected = answers.get("parent_service", mysql_services[0])
        answers.setdefault("smart_env", {})
        answers["smart_env"]["PMA_HOST"] = selected
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps


def _mongo_express_mapping(existing: list[str], answers: dict) -> None:
    """Mongo Express → MongoDB: ME_CONFIG_MONGODB_URL."""
    mongo_services = [s for s in existing if "mongodb" in s or "mongo" in s and "express" not in s]
    if mongo_services:
        selected = answers.get("parent_service", mongo_services[0])
        answers.setdefault("smart_env", {})
        answers["smart_env"]["ME_CONFIG_MONGODB_SERVER"] = selected
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps


def get_candidate_parents(service_name: str, existing_services: list[str]) -> list[str]:
    """Вернуть список кандидатов-родителей для smart mapping."""
    filters = {
        "pgadmin": lambda s: "postgres" in s,
        "kafka-ui": lambda s: "kafka" in s and "ui" not in s,
        "grafana": lambda s: "prometheus" in s,
        "phpmyadmin": lambda s: "mysql" in s or "mariadb" in s,
        "mongo-express": lambda s: ("mongodb" in s or "mongo" in s) and "express" not in s,
    }
    filt = filters.get(service_name)
    if filt:
        return [s for s in existing_services if filt(s)]
    return []

