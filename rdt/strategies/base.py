"""
BaseStrategy — shared docker-compose service block generation logic.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from rdt.presets.catalog import ServicePreset

NETWORK_NAME = "rambo-net"
CONTAINER_PREFIX = ""
DEFAULT_RESTART = "unless-stopped"


class BaseStrategy(ABC):
    """Base strategy: names, network, and restart policy."""

    def __init__(self, preset: ServicePreset, answers: dict[str, Any]) -> None:
        self.preset = preset
        self.answers = answers

    @property
    def container_name(self) -> str:
        custom = self.answers.get("container_name")
        if custom:
            return str(custom)
        return f"{CONTAINER_PREFIX}{self.preset.name}"

    def build(self) -> dict[str, Any]:
        """Build the final service dictionary for docker-compose."""
        service: dict[str, Any] = {}
        service["image"] = self.preset.image
        service["container_name"] = self.container_name
        service["restart"] = DEFAULT_RESTART

        host_port = self.answers.get("port", self.preset.default_port)
        net_type = self.answers.get("network_type", "bridge")
        expose_ports = self.answers.get("expose_ports", True)

        # host network_mode does not publish ports explicitly.
        if net_type == "host":
            service["network_mode"] = "host"
        else:
            # Ports.
            if expose_ports:
                service["ports"] = [f"{host_port}:{self.preset.container_port}"]
            else:
                service["expose"] = [str(self.preset.container_port)]

        # Environment variables.
        env = dict(self.preset.default_env)
        env.update(self.answers.get("extra_env", {}))
        if env:
            service["environment"] = env

        # Network (not needed for host or none).
        if net_type not in ("host", "none"):
            net_name = self.answers.get("network_name", NETWORK_NAME)
            service["networks"] = [net_name]

        # depends_on
        if deps := self.answers.get("depends_on"):
            svc_with_hc: set[str] = self.answers.get("services_with_healthcheck", set())
            service["depends_on"] = {
                dep: {
                    "condition": "service_healthy" if dep in svc_with_hc else "service_started"
                }
                for dep in deps
            }

        # Resource limits.
        if self.preset.deploy_limits:
            service["deploy"] = {
                "resources": {
                    "limits": {
                        "cpus": self.preset.deploy_limits["cpus"],
                        "memory": self.preset.deploy_limits["memory"],
                    }
                }
            }

        self._enrich(service)
        return service

    @abstractmethod
    def _enrich(self, service: dict[str, Any]) -> None:
        """Additional logic implemented by subclasses."""

