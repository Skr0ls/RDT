"""
AdminToolStrategy — поиск родительских сервисов, depends_on, без volumes.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import BaseStrategy, CONTAINER_PREFIX


class AdminToolStrategy(BaseStrategy):
    """Стратегия для Admin Tools: автосвязь с родительским сервисом."""

    def _enrich(self, service: dict[str, Any]) -> None:
        # Admin tools не используют volumes
        # depends_on уже проставлен в BaseStrategy через answers["depends_on"]
        # Добавляем smart-mapping env если передан
        smart_env = self.answers.get("smart_env", {})
        if smart_env:
            existing = service.get("environment", {})
            existing.update(smart_env)
            service["environment"] = existing

