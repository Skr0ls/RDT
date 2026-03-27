"""
TraefikStrategy — стратегия для Traefik reverse proxy.

Особенности:
- Монтирует /var/run/docker.sock (read-only) для auto-discovery
- Монтирует конфиг-файл traefik.yml из локальной папки
- Поддерживает несколько портов: HTTP (80), HTTPS (443), Dashboard (8080)
- Опциональный Let's Encrypt с хранением сертификатов в ./traefik/certs
- Healthcheck через ping-эндпоинт на порту API (8080)
"""
from __future__ import annotations

from typing import Any

from rdt.strategies.base import BaseStrategy

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

#: Дефолтная директория для конфига Traefik (относительно cwd)
DEFAULT_TRAEFIK_CONFIG_DIR = "./traefik"

#: Порт Dashboard по умолчанию
DEFAULT_DASHBOARD_PORT = 8080

#: Порт HTTPS по умолчанию
DEFAULT_HTTPS_PORT = 443


class TraefikStrategy(BaseStrategy):
    """
    Стратегия для Traefik reverse proxy.

    Отличия от BaseStrategy:
    - Перезаписывает ports: добавляет HTTPS и Dashboard
    - Использует bind-mounts (Docker socket + конфиг)
    - Добавляет healthcheck через /ping API-эндпоинт
    """

    def _enrich(self, service: dict[str, Any]) -> None:
        net_type = self.answers.get("network_type", "bridge")
        expose_ports = self.answers.get("expose_ports", True)

        # --- Порты ---
        if net_type not in ("host", "none") and expose_ports:
            http_port = self.answers.get("port", self.preset.default_port)
            dashboard_enabled = self.answers.get("traefik_dashboard", True)
            dashboard_port = self.answers.get("dashboard_port", DEFAULT_DASHBOARD_PORT)
            https_enabled = self.answers.get("traefik_https", False)
            https_port = self.answers.get("https_port", DEFAULT_HTTPS_PORT)

            ports: list[str] = [f"{http_port}:80"]

            if https_enabled:
                ports.append(f"{https_port}:443")

            if dashboard_enabled:
                ports.append(f"{dashboard_port}:8080")

            service["ports"] = ports

        # --- Volumes ---
        config_dir = self.answers.get("traefik_config_dir", DEFAULT_TRAEFIK_CONFIG_DIR)
        volumes: list[str] = [
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            f"{config_dir}/traefik.yml:/etc/traefik/traefik.yml:ro",
        ]

        if self.answers.get("traefik_https", False):
            volumes.append(f"{config_dir}/certs:/etc/traefik/certs")

        service["volumes"] = volumes

        # --- Healthcheck через ping ---
        service["healthcheck"] = {
            "test": ["CMD-SHELL", "wget -qO- http://localhost:8080/ping || exit 1"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 3,
            "start_period": "15s",
        }

