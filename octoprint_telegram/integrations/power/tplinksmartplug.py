from .base import PowerPlugin


class TPLinkSmartplugPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "tplinksmartplug"

    @property
    def plugin_name(self):
        return "TPLinkSmartplug"

    def get_plugs_data(self):
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

    def turn_on(self, plug_data):
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data):
        self._send_command("turnOff", plug_data)

    def _send_command(self, command, plug_data):
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"ip": plug_data})
