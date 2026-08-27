from .base import PowerPlugin


class PSUControlPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "psucontrol"

    @property
    def plugin_name(self):
        return "PSU Control"

    def get_plugs_data(self):
        is_on = False
        try:
            response = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "getPSUState")
            is_on = response.json().get("isPSUOn", False)
        except Exception:
            self._logger.exception("Caught an exception getting %s status", self.plugin_id)

        # Psucontrol is single plug, so data below is dummy
        return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

    def turn_on(self, plug_data):
        self._send_command("turnPSUOn")

    def turn_off(self, plug_data):
        self._send_command("turnPSUOff")

    def _send_command(self, command):
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command)
