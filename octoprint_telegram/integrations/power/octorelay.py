from .base import PowerPlugin


class OctoRelayPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "octorelay"

    @property
    def plugin_name(self):
        return "OctoRelay"

    def get_plugs_data(self):
        plugs_data = []

        plugs = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "listAllStatus").json()
        for plug in plugs:
            try:
                plug_id = plug["id"]
                label = plug.get("name") or f"RELAY{plug_id}"
                is_on = plug.get("status", False)

                plugs_data.append({"label": label, "is_on": is_on, "data": plug_id})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data):
        self._send_command(plug_data, True)

    def turn_off(self, plug_data):
        self._send_command(plug_data, False)

    def _send_command(self, plug_data, target):
        self.plugin_context.api.send_simpleapi_command(
            self.plugin_id, "update", {"subject": plug_data, "target": target}
        )
