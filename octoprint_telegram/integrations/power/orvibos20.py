from .base import PowerPlugin


class OrviboS20PowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "orvibos20"

    @property
    def plugin_name(self):
        return "OrviboS20"

    def get_plugs_data(self):
        plugs_data = []

        # OrviboS20 plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/cprasmu/OctoPrint-OrviboS20/blob/a40d0ad4184e48781ff1ebc7fb108eba1e084ba8/octoprint_orvibos20/__init__.py#L500
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "arrSmartplugs") or []
        for plug in plugs:
            try:
                plug_ip = plug["ip"]
                label = plug.get("label") or plug_ip

                is_on = False
                try:
                    # OrviboS20 plugin has no API for getting plug status, so we need to use the plugin functions
                    plugin_module = self.plugin_context.plugins.module(self.plugin_id)
                    is_on = plugin_module.Orvibo.discover(plug_ip).on
                except Exception:
                    self._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

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
