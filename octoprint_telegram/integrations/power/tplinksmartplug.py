from __future__ import annotations

from typing_extensions import override

from .base import PowerPlugin


class TPLinkSmartplugPowerPlugin(PowerPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "tplinksmartplug"

    @property
    @override
    def plugin_name(self) -> str:
        return "TPLinkSmartplug"

    @override
    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        plugs = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "getListPlug").json()
        for plug in plugs:
            try:
                plug_ip = plug["ip"]
                label = plug.get("label") or plug_ip
                is_on = plug.get("currentState", "").lower() == "on"

                plugs_data.append({"label": label, "is_on": is_on, "data": plug_ip})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    @override
    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnOn", plug_data)

    @override
    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"ip": plug_data})
