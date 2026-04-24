"""
DatabaseStrategy — required volumes, healthcheck, and credentials.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import BaseStrategy


class DatabaseStrategy(BaseStrategy):
    """Strategy for databases: volumes + healthcheck are required."""

    def _enrich(self, service: dict[str, Any]) -> None:
        # --- Volumes ---
        volume_source = self.answers.get("volume_source", f"{self.preset.name}_data")
        if self.preset.volumes:
            rendered_volumes = []
            for v in self.preset.volumes:
                rendered_volumes.append(v.replace("{{ volume_source }}", volume_source))
            service["volumes"] = rendered_volumes

        # --- Healthcheck ---
        if self.preset.healthcheck:
            hc = dict(self.preset.healthcheck)
            custom_hc = self.answers.get("healthcheck_params") or {}
            hc.update(custom_hc)
            service["healthcheck"] = hc

