"""
Управление .env и .env.example файлами.
"""
from __future__ import annotations
import re
import secrets
import string
from pathlib import Path

# Regex для извлечения имён переменных из ${VAR_NAME} в любом контексте
_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

# Переменные, которые считаются секретами
_PASSWORD_KEYS = {"PASSWORD", "SECRET", "PASS", "KEY", "TOKEN"}

# Стандартные credentials для каждого сервиса
SERVICE_DEFAULTS: dict[str, str] = {
    # PostgreSQL
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
    "POSTGRES_DB": "postgres",
    # MySQL
    "MYSQL_ROOT_PASSWORD": "root",
    "MYSQL_USER": "mysql",
    "MYSQL_PASSWORD": "mysql",
    "MYSQL_DATABASE": "mysql",
    # MariaDB
    "MARIADB_ROOT_PASSWORD": "root",
    "MARIADB_USER": "mariadb",
    "MARIADB_PASSWORD": "mariadb",
    "MARIADB_DATABASE": "mariadb",
    # MS SQL (должен соответствовать политике сложности)
    "MSSQL_SA_PASSWORD": "Sa_Password1!",
    # Oracle
    "ORACLE_PASSWORD": "oracle",
    "ORACLE_APP_USER": "app",
    "ORACLE_APP_PASSWORD": "oracle",
    # MongoDB
    "MONGO_USER": "mongo",
    "MONGO_PASSWORD": "mongo",
    "MONGO_DB": "mongo",
    # InfluxDB
    "INFLUXDB_USER": "influx",
    "INFLUXDB_PASSWORD": "influx",
    # Elasticsearch
    "ELASTIC_PASSWORD": "elastic",
    # OpenSearch (должен быть сложным)
    "OPENSEARCH_PASSWORD": "0penSearch!",
    # RabbitMQ
    "RABBITMQ_USER": "guest",
    "RABBITMQ_PASSWORD": "guest",
    # Keycloak
    "KEYCLOAK_ADMIN": "admin",
    "KEYCLOAK_ADMIN_PASSWORD": "admin",
    # Grafana
    "GRAFANA_USER": "admin",
    "GRAFANA_PASSWORD": "admin",
    # pgAdmin
    "PGADMIN_EMAIL": "admin@pgadmin.local",
    "PGADMIN_PASSWORD": "admin",
    # Kibana
    "KIBANA_SYSTEM_PASSWORD": "kibana",
    "KIBANA_ENCRYPTION_KEY": "changeme-32-chars-encryption-key",
    # Seq
    "SEQ_ADMIN_PASSWORD_HASH": "",
}


def is_secret_key(key: str) -> bool:
    return any(k in key.upper() for k in _PASSWORD_KEYS)


def generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _fallback_value(var_name: str) -> str:
    """Запасное значение если переменной нет в SERVICE_DEFAULTS."""
    u = var_name.upper()
    if is_secret_key(var_name):
        return "password"
    if "USER" in u or "ADMIN" in u:
        return "admin"
    if "EMAIL" in u:
        return "admin@example.local"
    if "DB" in u or "DATABASE" in u or "BUCKET" in u:
        return "app_db"
    return "app"


def get_env_values(preset_env: dict[str, str], hardcore: bool) -> dict[str, str]:
    """
    Возвращает конкретные значения для .env переменных.
    Использует regex для безопасного извлечения имён переменных из любого контекста.
    hardcore=True → генерировать уникальные пароли.
    """
    result: dict[str, str] = {}
    for placeholder in preset_env.values():
        for var_name in _VAR_PATTERN.findall(str(placeholder)):
            if var_name in result:
                continue
            if hardcore:
                result[var_name] = (
                    generate_password() if is_secret_key(var_name)
                    else SERVICE_DEFAULTS.get(var_name, _fallback_value(var_name))
                )
            else:
                result[var_name] = SERVICE_DEFAULTS.get(var_name, _fallback_value(var_name))
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

