"""
Manage .env and .env.example files.
"""
from __future__ import annotations
import re
import secrets
import string
from pathlib import Path

# Regex for extracting variable names from ${VAR_NAME} in any context.
_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

# Variables considered secrets.
_PASSWORD_KEYS = {"PASSWORD", "SECRET", "PASS", "KEY", "TOKEN"}

# Default credentials for each service.
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
    # MS SQL (must satisfy the complexity policy)
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
    # OpenSearch (must be complex)
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
    """Fallback value when a variable is not present in SERVICE_DEFAULTS."""
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
    Return concrete values for .env variables.
    Uses a regex to safely extract variable names from any context.
    hardcore=True means unique passwords are generated.
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
    """Append missing variables to the .env file."""
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


def extract_vars_from_text(text: str) -> set[str]:
    """Extract all ${VAR}-style variable names from arbitrary text."""
    return set(_VAR_PATTERN.findall(text))


def get_service_env_vars(data: Any, service_name: str) -> set[str]:
    """Return all ${VAR} variables used by a specific service in compose data."""
    import io
    try:
        from ruamel.yaml import YAML
        y = YAML()
        buf = io.StringIO()
        svc_block = (data.get("services") or {}).get(service_name)
        if svc_block is None:
            return set()
        y.dump({"tmp": svc_block}, buf)
        return extract_vars_from_text(buf.getvalue())
    except Exception:
        return set()


def get_all_env_vars_except(data: Any, exclude_service: str) -> set[str]:
    """Return all ${VAR} variables used by all services except the specified one."""
    import io
    result: set[str] = set()
    try:
        from ruamel.yaml import YAML
        y = YAML()
        for svc_name, svc_block in (data.get("services") or {}).items():
            if svc_name == exclude_service:
                continue
            if svc_block is None:
                continue
            buf = io.StringIO()
            y.dump({"tmp": svc_block}, buf)
            result |= extract_vars_from_text(buf.getvalue())
    except Exception:
        pass
    return result


def find_orphaned_vars(
    data: Any,
    service_name: str,
) -> set[str]:
    """Find ${VAR} variables used only by the service being removed.

    Returns variable names that can be safely removed from .env.
    """
    service_vars = get_service_env_vars(data, service_name)
    remaining_vars = get_all_env_vars_except(data, exclude_service=service_name)
    return service_vars - remaining_vars


def remove_vars_from_env_file(env_path: Path, vars_to_remove: set[str]) -> int:
    """Remove the specified variables from the .env file in place.

    Returns the number of removed lines.
    """
    if not env_path.exists() or not vars_to_remove:
        return 0

    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in vars_to_remove:
                removed += 1
                continue
        new_lines.append(line)

    # Remove trailing blank lines added by write_env.
    content = "".join(new_lines).rstrip("\n") + "\n" if new_lines else ""
    env_path.write_text(content, encoding="utf-8")
    return removed


def write_env_example(example_path: Path, values: dict[str, str]) -> None:
    """Write/update .env.example with empty values."""
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

