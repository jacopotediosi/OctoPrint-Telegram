from .base import PowerPlugin


class OctoHuePowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "octohue"

    @property
    def plugin_name(self):
        return "OctoHue"

    def get_plugs_data(self):
        is_on = False
        try:
            response = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "getstate")
            is_on = response.json().get("on", "").lower() == "true"
        except Exception:
            self._logger.exception("Caught an exception getting %s status", self.plugin_id)

        # Octohue is single plug, so data below is dummy
        return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

    def turn_on(self, plug_data):
        self._send_command("turnon")

    def turn_off(self, plug_data):
        self._send_command("turnoff")

    def _send_command(self, command):
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command)
