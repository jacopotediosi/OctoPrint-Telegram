from __future__ import annotations

from typing_extensions import override

from .base import PowerPlugin


class GpioControlPowerPlugin(PowerPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "gpiocontrol"

    @property
    @override
    def plugin_name(self) -> str:
        return "GPIO Control"

    @override
    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        # Gpiocontrol plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/catgiggle/OctoPrint-GpioControl/blob/37f698e51ff02493d833f43e14e88bdf54cd8b37/octoprint_gpiocontrol/__init__.py#L129
        try:
            statuses = self.plugin_context.api.send_simpleapi_get(self.plugin_id).json()
        except Exception:
            statuses = []
            self._logger.exception("Caught an exception getting %s plugs statuses", self.plugin_id)

        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "gpio_configurations") or []
        for index, configuration in enumerate(plugs):
            try:
                label = configuration.get("name") or f"GPIO{configuration['pin']}"
                is_on = index < len(statuses) and statuses[index].lower() == "on"

                plugs_data.append({"label": label, "is_on": is_on, "data": str(index)})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    @override
    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnGpioOn", plug_data)

    @override
    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnGpioOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"id": plug_data})
