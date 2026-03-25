"""
MonitoringStrategy — специфичные лимиты ресурсов и конфигурационные маппинги.
"""
from __future__ import annotations
from typing import Any

from rdt.strategies.base import BaseStrategy


class MonitoringStrategy(BaseStrategy):
    """Стратегия для мониторинга: volumes + healthcheck + config-маппинги."""

    def _enrich(self, service: dict[str, Any]) -> None:
        volume_source = self.answers.get("volume_source", f"rdt_{self.preset.name}_data")

        rendered_volumes = []
        for v in self.preset.volumes:
            rendered_volumes.append(v.replace("{{ volume_source }}", volume_source))

        if rendered_volumes:
            service["volumes"] = rendered_volumes

        if self.preset.healthcheck:
            service["healthcheck"] = dict(self.preset.healthcheck)

        # Дополнительные env-переменные от smart-mapping
        smart_env = self.answers.get("smart_env", {})
        if smart_env:
            existing = service.get("environment", {})
            existing.update(smart_env)
            service["environment"] = existing

