from __future__ import annotations

from .base import PowerPlugin


class WledPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "wled"

    @property
    def plugin_name(self) -> str:
        return "WLED"

    def get_plugs_data(self) -> list[dict]:
        is_on = False
        try:
            response = self.plugin_context.api.send_simpleapi_get(self.plugin_id)
            is_on = response.json().get("lights_on", False)
        except Exception:
            self._logger.exception("Caught an exception getting %s status", self.plugin_id)

        # Wled is single plug, so data below is dummy
        return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

    def turn_on(self, plug_data: str) -> None:
        self._send_command("lights_on")

    def turn_off(self, plug_data: str) -> None:
        self._send_command("lights_off")

    def _send_command(self, command: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command)
