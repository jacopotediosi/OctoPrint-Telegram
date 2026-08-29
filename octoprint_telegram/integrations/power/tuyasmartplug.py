from __future__ import annotations

from .base import PowerPlugin


class TuyaSmartplugPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "tuyasmartplug"

    @property
    def plugin_name(self) -> str:
        return "TuyaSmartplug"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        # Tuyasmartplug plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/ziirish/OctoPrint-TuyaSmartplug/blob/4344aeb6d9d59f4979d326a710656121d247e9af/octoprint_tuyasmartplug/__init__.py#L240
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "arrSmartplugs") or []
        for plug in plugs:
            try:
                label = plug["label"]

                is_on = False
                try:
                    # Tuyasmartplug plugin has no API for getting plug status, so we need to use the plugin functions
                    plugin_implementation = self.plugin_context.plugins.implementation(self.plugin_id)
                    is_on = plugin_implementation.is_turned_on(pluglabel=label)
                except Exception:
                    self._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                plugs_data.append({"label": label, "is_on": is_on, "data": label})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"label": plug_data})
