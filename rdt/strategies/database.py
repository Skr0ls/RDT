"""
DatabaseStrategy — обязательные volumes, healthcheck, credentials.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import BaseStrategy


class DatabaseStrategy(BaseStrategy):
    """Стратегия для баз данных: volumes + healthcheck обязательны."""

    def _enrich(self, service: dict[str, Any]) -> None:
        # --- Volumes ---
        volume_source = self.answers.get("volume_source", f"rdt_{self.preset.name}_data")
        if self.preset.volumes:
            rendered_volumes = []
            for v in self.preset.volumes:
                rendered_volumes.append(v.replace("{{ volume_source }}", volume_source))
            service["volumes"] = rendered_volumes

        # --- Healthcheck ---
        if self.preset.healthcheck:
            service["healthcheck"] = dict(self.preset.healthcheck)

