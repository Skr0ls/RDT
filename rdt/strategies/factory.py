"""
Strategy factory — returns the strategy required by a preset.
"""
from __future__ import annotations
from typing import Any

from rdt.presets.catalog import ServicePreset
from rdt.strategies.base import BaseStrategy
from rdt.strategies.database import DatabaseStrategy
from rdt.strategies.admin_tool import AdminToolStrategy
from rdt.strategies.monitoring import MonitoringStrategy
from rdt.strategies.web_server import WebServerStrategy
from rdt.strategies.traefik import TraefikStrategy


class _FallbackStrategy(BaseStrategy):
    """Used when no specific strategy exists."""
    def _enrich(self, service: dict) -> None:
        pass


def get_strategy(preset: ServicePreset, answers: dict[str, Any]) -> BaseStrategy:
    mapping = {
        "database": DatabaseStrategy,
        "admin_tool": AdminToolStrategy,
        "monitoring": MonitoringStrategy,
        "web_server": WebServerStrategy,
        "traefik": TraefikStrategy,
        "base": _FallbackStrategy,
    }
    cls = mapping.get(preset.strategy, _FallbackStrategy)
    return cls(preset, answers)

