from __future__ import annotations

import html

from typing_extensions import override

from .base import FilamentPlugin


class FilamentManagerFilamentPlugin(FilamentPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "filamentmanager"

    @property
    @override
    def plugin_name(self) -> str:
        return "FilamentManager"

    def _build_spool_description(self, spool: dict) -> str:
        parts = []

        if spool.get("name"):
            parts.append(spool["name"])

        profile = spool.get("profile", {})
        if profile.get("material"):
            parts.append(profile["material"])

        if profile.get("vendor"):
            parts.append(f"({profile['vendor']})")

        try:
            total_weight = spool.get("weight")
            used_weight = spool.get("used")
            if total_weight is not None and used_weight is not None:
                remaining_weight = int(total_weight - used_weight)
                parts.append(f"[{remaining_weight}g]")
        except Exception:
            pass

        return " ".join(parts) if parts else ""

    @override
    def list_spool(self) -> dict[str, str]:
        response = self.plugin_context.api.send_request(f"/plugin/{self.plugin_id}/spools", timeout=15)
        data = response.json()

        spool_dict = {}
        for spool in data.get("spools", []):
            spool_id = str(spool.get("id"))

            description = self._build_spool_description(spool)
            if description:
                spool_dict[spool_id] = description

        return spool_dict

    @override
    def get_spool_details_msg(self, spool_id: str) -> str:
        response = self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/spools/{spool_id}",
        )
        data = response.json()

        spool = data.get("spool", {})
        profile = spool.get("profile", {})

        id_str = str(spool.get("id") or "")
        name_str = str(spool.get("name") or "")
        vendor_str = str(profile.get("vendor") or "")
        material_str = str(profile.get("material") or "")
        cost_str = str(spool.get("cost") or "")
        density_str = str(profile.get("density") or "")
        diameter_str = str(profile.get("diameter") or "")

        total_weight = int(float(spool.get("weight") or 0))
        used_weight = int(float(spool.get("used") or 0))
        remaining_weight = total_weight - used_weight
        remaining_percent = int(100 / total_weight * remaining_weight) if total_weight > 0 else 0

        msg = (
            f"<b>ID</b>: {html.escape(id_str)}\n\n"
            f"<b>Name</b>: {html.escape(name_str)}\n"
            f"<b>Vendor</b>: {html.escape(vendor_str)}\n"
            f"<b>Material</b>: {html.escape(material_str)}\n\n"
            f"<b>Cost</b>: {html.escape(cost_str)}\n"
            f"<b>Density</b>: {html.escape(density_str)}g/cm&#179;\n"
            f"<b>Diameter</b>: {html.escape(diameter_str)}mm\n\n"
            f"<b>Total weight</b>: {total_weight}g\n"
            f"<b>Used</b>: {used_weight}g\n"
            f"<b>Remaining</b>: {remaining_weight}g ({remaining_percent}%)\n"
        )

        return msg

    @override
    def select_spool(self, tool_index: str, spool_id: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/selections/{tool_index}",
            "PATCH",
            json={"selection": {"tool": tool_index, "spool": {"id": spool_id}, "updateui": True}},
        )

    @override
    def deselect_spool(self, tool_index: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/selections/{tool_index}",
            "PATCH",
            json={"selection": {"tool": tool_index, "spool": {"id": None}, "updateui": True}},
        )

    @override
    def get_selected_spools(self) -> dict[int, str]:
        response = self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/selections",
        )
        data = response.json()
        selections = data.get("selections", [])

        selected_spools = {}

        for selection in selections:
            tool_number = selection.get("tool")
            if tool_number is None:
                continue

            spool = selection.get("spool", {})
            if not spool:
                continue

            description = self._build_spool_description(spool)
            if description:
                selected_spools[tool_number] = description

        return selected_spools
