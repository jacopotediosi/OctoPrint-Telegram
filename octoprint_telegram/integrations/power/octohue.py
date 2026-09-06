from __future__ import annotations

from typing_extensions import override

from .base import PowerPlugin


class OctoHuePowerPlugin(PowerPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "octohue"

    @property
    @override
    def plugin_name(self) -> str:
        return "OctoHue"

    @override
    def get_plugs_data(self) -> list[dict]:
        is_on = False
        try:
            response = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "getstate")
            is_on = response.json().get("on", "").lower() == "true"
        except Exception:
            self._logger.exception("Caught an exception getting %s status", self.plugin_id)

        # Octohue is single plug, so data below is dummy
        return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

    @override
    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnon")

    @override
    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnoff")

    def _send_command(self, command: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command)
