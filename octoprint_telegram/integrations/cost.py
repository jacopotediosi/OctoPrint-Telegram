from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octoprint.plugin import PluginSettings


class Cost:
    """The print cost rates configured in the Cost plugin."""

    def __init__(self, settings: PluginSettings):
        self._settings = settings

    @property
    def cost_per_time(self) -> float:
        return self._settings.global_get_float(["plugins", "cost", "cost_per_time"])

    @property
    def cost_per_length(self) -> float:
        return self._settings.global_get_float(["plugins", "cost", "cost_per_length"])

    @property
    def currency(self) -> str:
        return self._settings.global_get(["plugins", "cost", "currency"])
