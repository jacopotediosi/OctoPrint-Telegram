from __future__ import annotations

from .base import PowerPlugin


class IkeaTradfriPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "ikea_tradfri"

    @property
    def plugin_name(self) -> str:
        return "Ikea Tradfri"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        # Ikea_tradfri plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/ralmn/OctoPrint-Ikea-tradfri/blob/4c19c3588e3a2a85c7d78ed047062fb8d3994876/octoprint_ikea_tradfri/__init__.py#L547
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "selected_devices") or []
        for plug in plugs:
            try:
                plug_id = plug["id"]
                label = plug.get("name") or plug_id

                is_on = False
                try:
                    response = self.plugin_context.api.send_simpleapi_command(
                        self.plugin_id, "checkStatus", {"ip": plug_id}
                    )
                    is_on = response.json().get("currentState", "").lower() == "on"
                except Exception:
                    self._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                plugs_data.append({"label": label, "is_on": is_on, "data": plug_id})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"ip": plug_data})
