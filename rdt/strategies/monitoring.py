"""
MonitoringStrategy — monitoring-specific resource limits and config mappings.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import BaseStrategy


class MonitoringStrategy(BaseStrategy):
    """Strategy for monitoring services: volumes + healthcheck + config mappings."""

    def _enrich(self, service: dict[str, Any]) -> None:
        volume_source = self.answers.get("volume_source", f"{self.preset.name}_data")

        rendered_volumes = []
        for v in self.preset.volumes:
            rendered_volumes.append(v.replace("{{ volume_source }}", volume_source))

        if rendered_volumes:
            service["volumes"] = rendered_volumes

        if self.preset.healthcheck:
            hc = dict(self.preset.healthcheck)
            custom_hc = self.answers.get("healthcheck_params") or {}
            hc.update(custom_hc)
            service["healthcheck"] = hc

        # Additional env variables from smart mapping.
        smart_env = self.answers.get("smart_env", {})
        if smart_env:
            existing = service.get("environment", {})
            existing.update(smart_env)
            service["environment"] = existing

