from __future__ import annotations

from .base import PowerPlugin


class WemoSwitchPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "wemoswitch"

    @property
    def plugin_name(self) -> str:
        return "WemoSwitch"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        # Wemoswitch plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/jneilliii/OctoPrint-WemoSwitch/blob/70500edbff7eeda65efecc105f573e546cb8d661/octoprint_wemoswitch/__init__.py#L247
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "arrSmartplugs") or []
        for plug in plugs:
            try:
                plug_ip = plug["ip"]
                label = plug["label"] or plug_ip

                is_on = False
                try:
                    # Wemoswitch plugin has no API for getting plug status, so we need to use the plugin functions
                    plugin_implementation = self.plugin_context.plugins.implementation(self.plugin_id)
                    chk = plugin_implementation.sendCommand("info", plug_ip)
                    is_on = chk == 1 or chk == 8
                except Exception:
                    self._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                plugs_data.append({"label": label, "is_on": is_on, "data": plug_ip})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"ip": plug_data})
