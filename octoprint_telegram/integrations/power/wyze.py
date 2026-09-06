from __future__ import annotations

from typing_extensions import override

from .base import PowerPlugin


class WyzePowerPlugin(PowerPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "wyze"

    @property
    @override
    def plugin_name(self) -> str:
        return "Wyze"

    @override
    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        plugs = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "get_devices").json()
        for plug in plugs:
            try:
                label = plug["device_name"]
                is_on = False  # Wyze plugin does not support retrieving plugs status
                device_mac = plug["device_mac"]

                plugs_data.append({"label": label, "is_on": is_on, "data": device_mac})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    @override
    def turn_on(self, plug_data: str) -> None:
        self._send_command("turn_on", plug_data)

    @override
    def turn_off(self, plug_data: str) -> None:
        self._send_command("turn_off", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"device_mac": plug_data})
