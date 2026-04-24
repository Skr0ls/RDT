"""
Smart Mapping — automatic suggestions for links between services.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import CONTAINER_PREFIX

# Smart-link definitions: {service_name: handler_func}.
# A handler receives (existing_services: list[str], answers: dict) and updates answers["smart_env"].


def apply_smart_mapping(
    service_name: str,
    existing_services: list[str],
    answers: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply Smart Mapping for service_name.
    Return the updated answers dictionary.
    """
    handlers = {
        "pgadmin": _pgadmin_mapping,
        "kafka-ui": _kafka_ui_mapping,
        "grafana": _grafana_mapping,
        "phpmyadmin": _phpmyadmin_mapping,
        "mongo-express": _mongo_express_mapping,
        "logstash": _logstash_mapping,
        "filebeat": _filebeat_mapping,
        "kibana": _kibana_mapping,
    }
    handler = handlers.get(service_name)
    if handler:
        handler(existing_services, answers)
    return answers


def _pgadmin_mapping(existing: list[str], answers: dict) -> None:
    """pgAdmin → Postgres: fill in the database server."""
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


def _logstash_mapping(existing: list[str], answers: dict) -> None:
    """Logstash → Elasticsearch/OpenSearch: ES_HOST + depends_on + pipeline mode default."""
    es_services = [s for s in existing if "elasticsearch" in s or "opensearch" in s]
    if es_services:
        selected = answers.get("parent_service", es_services[0])
        answers.setdefault("smart_env", {})
        answers["smart_env"]["LOGSTASH_ES_HOST"] = f"{selected}:9200"
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps
        answers["parent_service"] = selected
        # Suggest the default pipeline mode without overriding an existing value.
        answers.setdefault("logstash_pipeline", "beats-es")
        answers.setdefault("logstash_es_host", f"{selected}:9200")


def _filebeat_mapping(existing: list[str], answers: dict) -> None:
    """Filebeat → Logstash (preferred) or Elasticsearch/OpenSearch + optional Kibana setup."""
    answers.setdefault("smart_env", {})

    # Priority: Logstash > Elasticsearch/OpenSearch
    logstash_services = [s for s in existing if "logstash" in s]
    es_services = [s for s in existing if "elasticsearch" in s or "opensearch" in s]
    kibana_services = [s for s in existing if "kibana" in s]

    if logstash_services:
        selected = answers.get("parent_service", logstash_services[0])
        answers["smart_env"]["FILEBEAT_LOGSTASH_HOST"] = f"{selected}:5044"
        answers.setdefault("filebeat_output", "logstash")
        answers.setdefault("filebeat_logstash_host", f"{selected}:5044")
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps
        answers["parent_service"] = selected

    elif es_services:
        selected = answers.get("parent_service", es_services[0])
        answers["smart_env"]["FILEBEAT_ES_HOST"] = f"{selected}:9200"
        answers.setdefault("filebeat_output", "elasticsearch")
        answers.setdefault("filebeat_es_host", f"{selected}:9200")
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps
        answers["parent_service"] = selected

    else:
        answers.setdefault("filebeat_output", "stdout")

    # Kibana setup (optional — configure dashboard setup if Kibana is present)
    if kibana_services:
        kibana_svc = kibana_services[0]
        answers["smart_env"]["FILEBEAT_KIBANA_HOST"] = f"{kibana_svc}:5601"
        answers.setdefault("filebeat_kibana_host", f"{kibana_svc}:5601")
        deps = answers.get("depends_on", [])
        if kibana_svc not in deps:
            deps.append(kibana_svc)
        answers["depends_on"] = deps

    # Set condition flags for artifact template selection
    output = answers.get("filebeat_output", "stdout")
    answers["filebeat_output_logstash"] = (output == "logstash")
    answers["filebeat_output_es"] = (output == "elasticsearch")
    answers["filebeat_output_stdout"] = (output == "stdout")


def _kibana_mapping(existing: list[str], answers: dict) -> None:
    """Kibana → Elasticsearch/OpenSearch: ELASTICSEARCH_HOSTS + depends_on."""
    es_services = [s for s in existing if "elasticsearch" in s or "opensearch" in s]
    if es_services:
        selected = answers.get("parent_service", es_services[0])
        answers.setdefault("smart_env", {})
        answers["smart_env"]["ELASTICSEARCH_HOSTS"] = f"http://{selected}:9200"
        deps = answers.get("depends_on", [])
        if selected not in deps:
            deps.append(selected)
        answers["depends_on"] = deps
        answers["parent_service"] = selected


def get_candidate_parents(service_name: str, existing_services: list[str]) -> list[str]:
    """Return the list of candidate parent services for smart mapping."""
    filters = {
        "pgadmin": lambda s: "postgres" in s,
        "kafka-ui": lambda s: "kafka" in s and "ui" not in s,
        "grafana": lambda s: "prometheus" in s,
        "phpmyadmin": lambda s: "mysql" in s or "mariadb" in s,
        "mongo-express": lambda s: ("mongodb" in s or "mongo" in s) and "express" not in s,
        "logstash": lambda s: "elasticsearch" in s or "opensearch" in s,
        "filebeat": lambda s: "logstash" in s or "elasticsearch" in s or "opensearch" in s or "kibana" in s,
        "kibana": lambda s: "elasticsearch" in s or "opensearch" in s,
    }
    filt = filters.get(service_name)
    if filt:
        return [s for s in existing_services if filt(s)]
    return []

