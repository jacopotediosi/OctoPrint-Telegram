from .base import PowerPlugin


class OctoLightHAPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "octolightHA"

    @property
    def plugin_name(self):
        return "OctoLight HA"

    def get_plugs_data(self):
        is_on = False
        try:
            response = self.plugin_context.api.send_simpleapi_get(self.plugin_id, {"action": "getState"})
            is_on = response.json().get("state", False)
        except Exception:
            self._logger.exception("Caught an exception getting %s status", self.plugin_id)

        # OctolightHA is single plug, so data below is dummy
        return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

    def turn_on(self, plug_data):
        self._send_command("turnOn")

    def turn_off(self, plug_data):
        self._send_command("turnOff")

    def _send_command(self, command):
        self.plugin_context.api.send_simpleapi_get(self.plugin_id, {"action": command})
