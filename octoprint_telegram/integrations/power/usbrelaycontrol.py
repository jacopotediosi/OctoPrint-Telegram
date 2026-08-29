from __future__ import annotations

from .base import PowerPlugin


class USBRelayControlPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "usbrelaycontrol"

    @property
    def plugin_name(self) -> str:
        return "USB Relay Control"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        # Usbrelaycontrol plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/abudden/OctoPrint-USBRelayControl/blob/0f06bccc06107f2b76fe360fed63698472c483cc/octoprint_usbrelaycontrol/__init__.py#L135
        try:
            statuses = self.plugin_context.api.send_simpleapi_get(self.plugin_id).json()
        except Exception:
            statuses = []
            self._logger.exception("Caught an exception getting %s plugs statuses", self.plugin_id)

        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "usbrelay_configurations") or []
        for index, configuration in enumerate(plugs):
            try:
                label = configuration["name"] or f"RELAY{configuration['relaynumber']}"
                is_on = index < len(statuses) and statuses[index].lower() == "on"

                plugs_data.append({"label": label, "is_on": is_on, "data": index})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnUSBRelayOn", plug_data)

    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnUSBRelayOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"id": plug_data})
