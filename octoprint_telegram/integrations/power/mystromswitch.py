from __future__ import annotations

import requests
from typing_extensions import override

from .base import PowerPlugin


class MyStromSwitchPowerPlugin(PowerPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "mystromswitch"

    @property
    @override
    def plugin_name(self) -> str:
        return "MyStromSwitch"

    @override
    def get_plugs_data(self) -> list[dict]:
        is_on = False
        try:
            # Mystromswitch plugin has no API nor plugin functions for getting plug status, so below code is copied from the plugin code:
            # https://github.com/da4id/OctoPrint-MyStromSwitch/blob/e7bf0762d39938fb81b1d2d1945336df0e96d103/octoprint_mystromswitch/__init__.py#L180
            ip = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "ip")
            token = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "token")

            response = requests.get(f"http://{ip}/report", headers={"Token": token}, timeout=5)
            is_on = response.json().get("relay", False)
        except Exception:
            self._logger.exception("Caught an exception getting %s status", self.plugin_id)

        # Mystromswitch is single plug, so data below is dummy
        return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

    @override
    def turn_on(self, plug_data: str) -> None:
        self._send_command("enableRelais")

    @override
    def turn_off(self, plug_data: str) -> None:
        self._send_command("disableRelais")

    def _send_command(self, command: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command)
