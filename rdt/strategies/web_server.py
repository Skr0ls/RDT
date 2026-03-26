"""
WebServerStrategy — стратегия для веб-серверов (nginx, apache и подобных).

Особенности:
- volumes как bind-mounts (не named volumes)
- конфиг монтируется из локальной папки
- для static/spa/php дополнительно монтируется директория с контентом
- healthcheck через wget
"""
from __future__ import annotations

from typing import Any

from rdt.strategies.base import BaseStrategy

# ---------------------------------------------------------------------------
# Nginx
# ---------------------------------------------------------------------------

#: Nginx-режимы, которые требуют монтирования html-директории
_HTML_MODES = {"nginx-static", "nginx-spa"}

#: Дефолтная директория для конфига nginx (относительно cwd)
DEFAULT_CONFIG_DIR = "./nginx"

#: Дефолтная директория для html (относительно cwd)
DEFAULT_HTML_DIR = "./nginx/html"

# ---------------------------------------------------------------------------
# Apache
# ---------------------------------------------------------------------------

#: Apache-режимы (все пресеты на базе Apache)
_APACHE_MODES = {"apache-static", "apache-php"}

#: Дефолтная директория для конфига Apache (относительно cwd)
DEFAULT_APACHE_CONFIG_DIR = "./apache"

#: Дефолтная директория для html у apache-static (относительно cwd)
DEFAULT_APACHE_HTML_DIR = "./apache/html"

#: Дефолтная директория исходников PHP-приложения (относительно cwd)
DEFAULT_APACHE_SRC_DIR = "./src"


class WebServerStrategy(BaseStrategy):
    """
    Стратегия для веб-серверов (nginx и apache).

    Отличия от BaseStrategy:
    - не использует named volumes — только bind-mounts
    - маршрутизирует enrich-логику по семейству сервера
    - добавляет healthcheck через wget
    """

    def _enrich(self, service: dict[str, Any]) -> None:
        if self.preset.name in _APACHE_MODES:
            self._enrich_apache(service)
        else:
            self._enrich_nginx(service)

        # Общий healthcheck для всех веб-серверов
        service["healthcheck"] = {
            "test": ["CMD-SHELL", "wget -qO /dev/null http://localhost/ || exit 1"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 3,
            "start_period": "15s",
        }

    # ------------------------------------------------------------------
    # Nginx
    # ------------------------------------------------------------------

    def _enrich_nginx(self, service: dict[str, Any]) -> None:
        config_dir = self.answers.get("nginx_config_dir", DEFAULT_CONFIG_DIR)
        volumes: list[str] = [
            f"{config_dir}/nginx.conf:/etc/nginx/nginx.conf:ro",
        ]

        if self.preset.name in _HTML_MODES:
            html_dir = self.answers.get("nginx_html_dir", DEFAULT_HTML_DIR)
            volumes.append(f"{html_dir}:/usr/share/nginx/html:ro")

        service["volumes"] = volumes

    # ------------------------------------------------------------------
    # Apache
    # ------------------------------------------------------------------

    def _enrich_apache(self, service: dict[str, Any]) -> None:
        config_dir = self.answers.get("apache_config_dir", DEFAULT_APACHE_CONFIG_DIR)

        if self.preset.name == "apache-static":
            volumes: list[str] = [
                f"{config_dir}/httpd.conf:/usr/local/apache2/conf/httpd.conf:ro",
            ]
            html_dir = self.answers.get("apache_html_dir", DEFAULT_APACHE_HTML_DIR)
            volumes.append(f"{html_dir}:/usr/local/apache2/htdocs:ro")

        else:  # apache-php
            volumes = [
                f"{config_dir}/vhost.conf:/etc/apache2/sites-available/000-default.conf:ro",
            ]
            src_dir = self.answers.get("apache_src_dir", DEFAULT_APACHE_SRC_DIR)
            volumes.append(f"{src_dir}:/var/www/html")

        service["volumes"] = volumes

