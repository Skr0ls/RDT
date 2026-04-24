"""
WebServerStrategy — strategy for web servers such as nginx and apache.

Features:
- volumes are bind mounts instead of named volumes
- config is mounted from a local directory
- static/spa/php modes additionally mount a content directory
- healthcheck uses wget
"""
from __future__ import annotations

from typing import Any

from rdt.strategies.base import BaseStrategy

# ---------------------------------------------------------------------------
# Nginx
# ---------------------------------------------------------------------------

#: Nginx modes that require mounting an html directory.
_HTML_MODES = {"nginx-static", "nginx-spa"}

#: Default nginx config directory relative to cwd.
DEFAULT_CONFIG_DIR = "./nginx"

#: Default html directory relative to cwd.
DEFAULT_HTML_DIR = "./nginx/html"

# ---------------------------------------------------------------------------
# Apache
# ---------------------------------------------------------------------------

#: Apache modes (all Apache-based presets).
_APACHE_MODES = {"apache-static", "apache-php"}

#: Default Apache config directory relative to cwd.
DEFAULT_APACHE_CONFIG_DIR = "./apache"

#: Default html directory for apache-static relative to cwd.
DEFAULT_APACHE_HTML_DIR = "./apache/html"

#: Default PHP application source directory relative to cwd.
DEFAULT_APACHE_SRC_DIR = "./src"


class WebServerStrategy(BaseStrategy):
    """
    Strategy for web servers (nginx and apache).

    Differences from BaseStrategy:
    - does not use named volumes, only bind mounts
    - routes enrich logic by server family
    - adds a wget-based healthcheck
    """

    def _enrich(self, service: dict[str, Any]) -> None:
        if self.preset.name in _APACHE_MODES:
            self._enrich_apache(service)
        else:
            self._enrich_nginx(service)

        # Shared healthcheck for all web servers.
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

