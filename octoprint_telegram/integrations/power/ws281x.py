from __future__ import annotations

from .base import PowerPlugin


class WS281xPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "ws281x_led_status"

    @property
    def plugin_name(self) -> str:
        return "WS281x"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        plugs_names = ["lights", "torch"]

        statuses = {}
        try:
            statuses = self.plugin_context.api.send_simpleapi_get(self.plugin_id).json()
        except Exception:
            self._logger.exception("Caught an exception getting %s plugs statuses", self.plugin_id)

        for plug_name in plugs_names:
            try:
                label = f"{self.plugin_name} {plug_name}"
                is_on = statuses.get(f"{plug_name}_on", False)

                plugs_data.append({"label": label, "is_on": is_on, "data": plug_name})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command(f"{plug_data}_on")

    def turn_off(self, plug_data: str) -> None:
        self._send_command(f"{plug_data}_off")

    def _send_command(self, command: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command)
