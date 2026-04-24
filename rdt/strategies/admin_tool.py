"""
AdminToolStrategy — parent-service lookup, depends_on, no volumes.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import BaseStrategy, CONTAINER_PREFIX


class AdminToolStrategy(BaseStrategy):
    """Strategy for Admin Tools: auto-link with a parent service."""

    def _enrich(self, service: dict[str, Any]) -> None:
        # Admin tools do not use volumes.
        # depends_on is already set by BaseStrategy via answers["depends_on"].
        # Add smart-mapping env values when provided.
        smart_env = self.answers.get("smart_env", {})
        if smart_env:
            existing = service.get("environment", {})
            existing.update(smart_env)
            service["environment"] = existing

