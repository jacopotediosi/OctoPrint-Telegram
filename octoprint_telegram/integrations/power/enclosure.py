from __future__ import annotations

from urllib.parse import quote

from typing_extensions import override

from .base import PowerPlugin


class EnclosurePowerPlugin(PowerPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "enclosure"

    @property
    @override
    def plugin_name(self) -> str:
        return "Enclosure"

    @override
    def get_plugs_data(self) -> list[dict]:
        plugs_data = []

        plugs = self.plugin_context.api.send_request(f"/plugin/{self.plugin_id}/outputs").json()
        for plug in plugs:
            try:
                plug_index = str(plug["index_id"])
                label = plug.get("label") or plug_index
                is_on = plug.get("State", "").strip().lower() == "on"

                plugs_data.append({"label": label, "is_on": is_on, "data": plug_index})
            except Exception:
                self._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

        return plugs_data

    @override
    def turn_on(self, plug_data: str) -> None:
        self._send_command(True, plug_data)

    @override
    def turn_off(self, plug_data: str) -> None:
        self._send_command(False, plug_data)

    def _send_command(self, status: bool, plug_data: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/outputs/{quote(plug_data, safe='')}", "PATCH", json={"status": status}
        )
