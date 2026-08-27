import requests

from ...utils import StringUtils
from .base import PowerPlugin


class DomoticzPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self):
        return "domoticz"

    @property
    def plugin_name(self):
        return "Domoticz"

    def get_plugs_data(self):
        plugs_data = []

        # Domoticz plugin has no API for getting plugs. Below code is copied from the plugin code:
        # https://github.com/jneilliii/OctoPrint-Domoticz/blob/a3e1d6fddbe6a8b09faf53f62e519f8499e4cc82/octoprint_domoticz/__init__.py#L147
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "arrSmartplugs") or []
        for plug in plugs:
            try:
                ip = plug["ip"]
                idx = plug["idx"]
                username = plug.get("username", "")
                password = plug.get("password", "")
                passcode = plug.get("passcode", "")

                label = plug.get("label") or f"{ip}|{idx}"

                is_on = False
                try:
                    # Domoticz plugin has no API nor plugin functions for getting plug status, so below code is copied from the plugin code:
                    # https://github.com/jneilliii/OctoPrint-Domoticz/blob/a3e1d6fddbe6a8b09faf53f62e519f8499e4cc82/octoprint_domoticz/__init__.py#L241
                    str_url = f"{ip}/json.htm?type=command&param=getdevices&rid={idx}"
                    if passcode != "":
                        str_url = f"{str_url}&passcode={passcode}"
                    if username != "":
                        response = requests.get(str_url, auth=(username, password), timeout=10, verify=False)
                    else:
                        response = requests.get(str_url, timeout=10, verify=False)
                    is_on = response.json()["result"][0]["Status"].lower() == "on"
                except Exception:
                    self._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                escaped_ip = ip.replace("|", "\\|")
                escaped_idx = idx.replace("|", "\\|")
                data = f"{escaped_ip}|{escaped_idx}"

                plugs_data.append({"label": label, "is_on": is_on, "data": data})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data):
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data):
        self._send_command("turnOff", plug_data)

    def _send_command(self, command, plug_data):
        ip, idx = StringUtils.split_with_escape_handling(plug_data, "|")

        selected_plug = None
        plugs = self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "arrSmartplugs") or []
        for plug in plugs:
            if plug.get("ip") == ip and plug.get("idx") == idx:
                selected_plug = plug
                break
        if not selected_plug:
            raise RuntimeError(f"Plug {plug_data} not found")

        username = selected_plug["username"]
        password = selected_plug["password"]
        passcode = selected_plug["passcode"]

        self.plugin_context.api.send_simpleapi_command(
            self.plugin_id,
            command,
            {
                "ip": ip,
                "idx": idx,
                "username": username,
                "password": password,
                "passcode": passcode,
            },
        )
