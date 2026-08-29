from __future__ import annotations

import html

from ...emoji import Emoji
from .base import FilamentPlugin

render_emojis = Emoji.render_emojis


class SpoolmanFilamentPlugin(FilamentPlugin):
    @property
    def plugin_id(self) -> str:
        return "Spoolman"

    @property
    def plugin_name(self) -> str:
        return "Spoolman"

    def _build_spool_description(self, spool: dict) -> str:
        filament = spool.get("filament", {})
        vendor = filament.get("vendor", {})

        parts = [
            filament.get("name"),
            filament.get("material"),
            f"({vendor['name']})" if vendor.get("name") else None,
            f"[{spool['remaining_weight']}g]" if spool.get("remaining_weight") is not None else None,
        ]

        return " ".join(filter(None, parts))

    def list_spool(self) -> dict[str, str]:
        response = self.plugin_context.api.send_request(f"/plugin/{self.plugin_id}/spoolman/spools", timeout=15)
        data = response.json().get("data", {})

        spool_dict = {}
        for spool in data.get("spools", []):
            spool_id = str(spool.get("id"))

            description = self._build_spool_description(spool)
            if description:
                spool_dict[spool_id] = description

        return spool_dict

    def get_spool_details_msg(self, spool_id: str) -> str:
        response = self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/spoolman/spools",
        )
        data = response.json().get("data", {})

        spool_id_str = str(spool_id)

        for spool in data.get("spools", []):
            current_spool_id_str = str(spool.get("id"))

            if current_spool_id_str == spool_id_str:
                filament = spool.get("filament", {})
                vendor = filament.get("vendor", {})

                # Section 1: id, lot nr
                section1_parts = []
                section1_parts.append(f"<b>ID</b>: {html.escape(current_spool_id_str)}")
                lot_str = str(spool.get("lot_nr") or "").strip()
                if lot_str:
                    section1_parts.append(f"<b>Lot Nr</b>: {html.escape(lot_str)}")

                # Section 2: filament name, vendor name, filament material
                section2_parts = []
                filament_name_str = str(filament.get("name") or "").strip()
                if filament_name_str:
                    section2_parts.append(f"<b>Filament name</b>: {html.escape(filament_name_str)}")
                vendor_str = str(vendor.get("name") or "").strip()
                if vendor_str:
                    section2_parts.append(f"<b>Vendor</b>: {html.escape(vendor_str)}")
                material_str = str(filament.get("material") or "").strip()
                if material_str:
                    section2_parts.append(f"<b>Material</b>: {html.escape(material_str)}")

                # Section 3: location, price
                section3_parts = []
                location_str = str(spool.get("location") or "").strip()
                if location_str:
                    section3_parts.append(f"<b>Location</b>: {html.escape(location_str)}")
                price_str = str(spool.get("price") or "").strip()
                if price_str:
                    section3_parts.append(f"<b>Price</b>: {html.escape(price_str)}")

                # Section 4: density, diameter
                section4_parts = []
                density_str = str(filament.get("density") or "").strip()
                if density_str:
                    section4_parts.append(f"<b>Density</b>: {html.escape(density_str)}g/cm&#179;")
                diameter_str = str(filament.get("diameter") or "").strip()
                if diameter_str:
                    section4_parts.append(f"<b>Diameter</b>: {html.escape(diameter_str)}mm")

                # Section 5: registered date, first use, last use
                section5_parts = []
                registered_str = str(spool.get("registered") or "").strip()
                if registered_str:
                    section5_parts.append(f"<b>Registered</b>: {html.escape(registered_str)}")
                first_use_str = str(spool.get("first_used") or "").strip()
                if first_use_str:
                    section5_parts.append(f"<b>First use</b>: {html.escape(first_use_str)}")
                last_use_str = str(spool.get("last_used") or "").strip()
                if last_use_str:
                    section5_parts.append(f"<b>Last use</b>: {html.escape(last_use_str)}")

                # Section 6: lengths and weights
                section6_parts = []

                initial_parts = []
                initial_weight = spool.get("initial_weight") or 0
                initial_weight_str = str(initial_weight)
                if initial_weight_str:
                    initial_parts.append(f"{initial_weight_str}g")
                spool_weight_str = str(spool.get("spool_weight") or "").strip()
                if spool_weight_str:
                    initial_parts.append(f"(plus {spool_weight_str}g of empty spool)")
                initial_str = " ".join(initial_parts)
                if initial_str:
                    section6_parts.append(f"<b>Initial</b>: {html.escape(initial_str)}")

                remaining_weight = int(spool.get("remaining_weight") or 0)
                remaining_length = int(spool.get("remaining_length") or 0)
                remaining_percent = int(100 / initial_weight * remaining_weight) if initial_weight > 0 else 0
                section6_parts.append(
                    f"<b>Remaining</b>: {remaining_weight}g {remaining_length}mm ({remaining_percent}%)"
                )

                # Section 7: comment and extra fields
                section7_parts = []

                comment_str = str(spool.get("comment") or "").strip()
                if comment_str:
                    section7_parts.append(f"<b>Comment</b>:\n<pre>{html.escape(comment_str)}</pre>")

                extra = spool.get("extra", {})
                for key, value in extra.items():
                    section7_parts.append(f"<b>{html.escape(key)}</b>:\n<code>{html.escape(str(value))}</code>")

                # Build the final message by joining non-empty sections
                sections = []
                if section1_parts:
                    sections.append("\n".join(section1_parts))
                if section2_parts:
                    sections.append("\n".join(section2_parts))
                if section3_parts:
                    sections.append("\n".join(section3_parts))
                if section4_parts:
                    sections.append("\n".join(section4_parts))
                if section5_parts:
                    sections.append("\n".join(section5_parts))
                if section6_parts:
                    sections.append("\n".join(section6_parts))
                if section7_parts:
                    sections.append("\n".join(section7_parts))

                return "\n\n".join(sections)

        return render_emojis("{emo:attention} Spool not found")

    def select_spool(self, tool_index: str, spool_id: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/self/spool",
            "POST",
            json={"spoolId": spool_id, "toolIdx": tool_index},
        )

    def deselect_spool(self, tool_index: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/self/spool",
            "POST",
            json={"toolIdx": tool_index},
        )

    def get_selected_spools(self) -> dict[int, str]:
        response = self.plugin_context.api.send_request(f"/plugin/{self.plugin_id}/spoolman/spools", timeout=15)
        spools = response.json().get("data", {}).get("spools", [])

        selected_spools_config = (
            self.plugin_context.octoprint_settings.plugin_setting(self.plugin_id, "selectedSpoolIds") or {}
        )

        selected_spools = {}
        for tool_index, config in selected_spools_config.items():
            spool_id = config.get("spoolId")
            if spool_id:
                for spool in spools:
                    if str(spool["id"]) == str(spool_id):
                        selected_spools[int(tool_index)] = self._build_spool_description(spool)
                        break

        return selected_spools
