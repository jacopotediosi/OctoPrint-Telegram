from __future__ import annotations

from ...utils import StringUtils
from .base import PowerPlugin


class TasmotaPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "tasmota"

    @property
    def plugin_name(self) -> str:
        return "Tasmota"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        # Tasmota plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/jneilliii/OctoPrint-Tasmota/blob/49c7e01f4a077d0d650931fd91f3b63cfef780c2/octoprint_tasmota/__init__.py#L816
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "arrSmartplugs") or []
        for plug in plugs:
            try:
                plug_ip = plug["ip"]
                plug_idx = plug["idx"]
                label = plug.get("label") or f"{plug_ip}|{plug_idx}"

                is_on = False
                try:
                    response = self.plugin_context.api.send_simpleapi_command(
                        self.plugin_id, "checkStatus", {"ip": plug_ip, "idx": plug_idx}
                    )
                    is_on = response.json().get("currentState", "").lower() == "on"
                except Exception:
                    self._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                escaped_ip = plug_ip.replace("|", "\\|")
                escaped_idx = plug_idx.replace("|", "\\|")
                data = f"{escaped_ip}|{escaped_idx}"

                plugs_data.append({"label": label, "is_on": is_on, "data": data})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        ip, idx = StringUtils.split_with_escape_handling(plug_data, "|")
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"ip": ip, "idx": idx})
