"""
BaseStrategy — общая логика генерации docker-compose блока.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from rdt.presets.catalog import ServicePreset

NETWORK_NAME = "rambo-net"
CONTAINER_PREFIX = ""
DEFAULT_RESTART = "unless-stopped"


class BaseStrategy(ABC):
    """Базовая стратегия: имена, сеть, рестарт-политика."""

    def __init__(self, preset: ServicePreset, answers: dict[str, Any]) -> None:
        self.preset = preset
        self.answers = answers

    @property
    def container_name(self) -> str:
        return f"{CONTAINER_PREFIX}{self.preset.name}"

    def build(self) -> dict[str, Any]:
        """Собрать итоговый словарь сервиса для docker-compose."""
        service: dict[str, Any] = {}
        service["image"] = self.preset.image
        service["container_name"] = self.container_name
        service["restart"] = DEFAULT_RESTART

        # Порты
        host_port = self.answers.get("port", self.preset.default_port)
        service["ports"] = [f"{host_port}:{self.preset.container_port}"]

        # Переменные окружения
        env = dict(self.preset.default_env)
        env.update(self.answers.get("extra_env", {}))
        if env:
            service["environment"] = env

        # Сеть
        service["networks"] = [NETWORK_NAME]

        # depends_on
        if deps := self.answers.get("depends_on"):
            service["depends_on"] = {
                dep: {"condition": "service_healthy"} for dep in deps
            }

        # Лимиты ресурсов
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
        """Дополнительная логика в подклассах."""

