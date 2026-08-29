from __future__ import annotations

from ...utils import StringUtils
from .base import PowerPlugin


class TasmotaMQTTPowerPlugin(PowerPlugin):
    @property
    def plugin_id(self) -> str:
        return "tasmota_mqtt"

    @property
    def plugin_name(self) -> str:
        return "TasmotaMQTT"

    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        plugs = self.plugin_context.api.send_simpleapi_command(self.plugin_id, "getListPlug").json()
        for plug in plugs:
            try:
                is_on = plug.get("currentstate", "").lower() == "on"

                label = plug.get("label") or f"{plug['topic']}|{plug['relayN']}"

                escaped_topic = plug["topic"].replace("|", "\\|")
                escaped_relay = plug["relayN"].replace("|", "\\|")
                data = f"{escaped_topic}|{escaped_relay}"

                plugs_data.append({"label": label, "is_on": is_on, "data": data})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    def turn_on(self, plug_data: str) -> None:
        self._send_command("turnOn", plug_data)

    def turn_off(self, plug_data: str) -> None:
        self._send_command("turnOff", plug_data)

    def _send_command(self, command: str, plug_data: str) -> None:
        topic, relay_n = StringUtils.split_with_escape_handling(plug_data, "|")
        self.plugin_context.api.send_simpleapi_command(self.plugin_id, command, {"topic": topic, "relayN": relay_n})
