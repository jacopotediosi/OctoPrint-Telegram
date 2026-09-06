from __future__ import annotations

import html

from typing_extensions import override

from ...emoji import Emoji
from .base import FilamentPlugin

render_emojis = Emoji.render_emojis


class SpoolManagerFilamentPlugin(FilamentPlugin):
    @property
    @override
    def plugin_id(self) -> str:
        return "SpoolManager"

    @property
    @override
    def plugin_name(self) -> str:
        return "SpoolManager"

    def _build_spool_description(self, spool: dict) -> str:
        parts = list(
            filter(
                None,
                [
                    spool.get("displayName"),
                    spool.get("material"),
                    spool.get("colorName"),
                    f"({spool['vendor']})" if spool.get("vendor") else None,
                ],
            )
        )

        try:
            if spool.get("remainingWeight"):
                remaining_weight = int(float(spool["remainingWeight"]))
                parts.append(f"[{remaining_weight}g]")
        except Exception:
            pass

        return " ".join(parts) if parts else ""

    @override
    def list_spool(self) -> dict[str, str]:
        response = self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/loadSpoolsByQuery?selectedPageSize=all&sortColumn=displayName&sortOrder=asc&filterName=hideInactiveSpools",
            timeout=15,
        )
        data = response.json()

        spool_dict = {}
        for spool in data.get("allSpools", []):
            spool_id = str(spool.get("databaseId"))

            description = self._build_spool_description(spool)
            if description:
                spool_dict[spool_id] = description

        return spool_dict

    @override
    def get_spool_details_msg(self, spool_id: str) -> str:
        response = self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/loadSpoolsByQuery?selectedPageSize=all&sortColumn=displayName&sortOrder=asc&filterName=hideInactiveSpools",
            timeout=15,
        )
        data = response.json()

        spool_id_str = str(spool_id)

        for spool in data.get("allSpools", []):
            current_spool_id_str = str(spool.get("databaseId"))

            if current_spool_id_str == spool_id_str:
                # Section 1: id, serial
                section1_parts = []
                section1_parts.append(f"<b>ID</b>: {html.escape(current_spool_id_str)}")
                serial_str = str(spool.get("code") or "").strip()
                if serial_str:
                    section1_parts.append(f"<b>Serial</b>: {html.escape(serial_str)}")

                # Section 2: name, vendor, material, color
                section2_parts = []
                name_str = str(spool.get("displayName") or "").strip()
                if name_str:
                    section2_parts.append(f"<b>Name</b>: {html.escape(name_str)}")
                vendor_str = str(spool.get("vendor") or "").strip()
                if vendor_str:
                    section2_parts.append(f"<b>Vendor</b>: {html.escape(vendor_str)}")
                material_str = str(spool.get("material") or "").strip()
                if material_str:
                    section2_parts.append(f"<b>Material</b>: {html.escape(material_str)}")
                color_str = str(spool.get("colorName") or "").strip()
                if color_str:
                    section2_parts.append(f"<b>Color</b>: {html.escape(color_str)}")

                # Section 3: purchased from, cost
                section3_parts = []
                purchased_from_str = str(spool.get("purchasedFrom") or "").strip()
                if purchased_from_str:
                    section3_parts.append(f"<b>Purchased from</b>: {html.escape(purchased_from_str)}")
                cost_str = str(spool.get("cost") or "").strip()
                cost_unit_str = str(spool.get("costUnit") or "").strip()
                if cost_str:
                    section3_parts.append(f"<b>Cost</b>: {html.escape(cost_str + cost_unit_str)}")

                # Section 4: temperatures (tool, bed, enclosure), flowrate
                section4_parts = []
                temperature_str = str(spool.get("temperature") or "").strip()
                if temperature_str:
                    section4_parts.append(f"<b>Tool temp</b>: {html.escape(temperature_str)}°C")
                bed_temperature_str = str(spool.get("bedTemperature") or "").strip()
                if bed_temperature_str:
                    section4_parts.append(f"<b>Bed temp</b>: {html.escape(bed_temperature_str)}°C")
                enclosure_temperature_str = str(spool.get("enclosureTemperature") or "").strip()
                if enclosure_temperature_str:
                    section4_parts.append(f"<b>Enclosure temp</b>: {html.escape(enclosure_temperature_str)}°C")
                flowrate_compensation_str = str(spool.get("flowRateCompensation") or "").strip()
                if flowrate_compensation_str:
                    section4_parts.append(f"<b>Flowrate compensation</b>: {html.escape(flowrate_compensation_str)}%")

                # Section 5: density, diameter
                section5_parts = []
                density_str = str(spool.get("density") or "").strip()
                if density_str:
                    section5_parts.append(f"<b>Density</b>: {html.escape(density_str)}g/cm&#179;")
                diameter_str = str(spool.get("diameter") or "").strip()
                diameter_tolerance_str = str(spool.get("diameterTolerance") or "").strip()
                if diameter_str:
                    tolerance_part = f" &#177;{html.escape(diameter_tolerance_str)}" if diameter_tolerance_str else ""
                    section5_parts.append(f"<b>Diameter</b>: {html.escape(diameter_str)}mm{tolerance_part}")

                # Section 6: purchased on, created, updated, first use, last use
                section6_parts = []
                purchased_on_str = str(spool.get("purchasedOn") or "").strip()
                if purchased_on_str:
                    section6_parts.append(f"<b>Purchased on</b>: {html.escape(purchased_on_str)}")
                created_str = str(spool.get("created") or "").strip()
                if created_str:
                    section6_parts.append(f"<b>Created</b>: {html.escape(created_str)}")
                updated_str = str(spool.get("updated") or "").strip()
                if updated_str:
                    section6_parts.append(f"<b>Updated</b>: {html.escape(updated_str)}")
                first_use_str = str(spool.get("firstUse") or "").strip()
                if first_use_str:
                    section6_parts.append(f"<b>First use</b>: {html.escape(first_use_str)}")
                last_use_str = str(spool.get("lastUse") or "").strip()
                if last_use_str:
                    section6_parts.append(f"<b>Last use</b>: {html.escape(last_use_str)}")

                # Section 7: lengths and weights
                section7_parts = []

                total_parts = []
                total_weight_str = str(spool.get("totalWeight") or "").strip()
                if total_weight_str:
                    total_parts.append(f"{total_weight_str}g")
                spool_weight_str = str(spool.get("spoolWeight") or "").strip()
                if spool_weight_str:
                    total_parts.append(f"(plus {spool_weight_str}g of empty spool)")
                total_length_str = str(spool.get("totalLength") or "").strip()
                if total_length_str:
                    total_parts.append(f"{total_length_str}mm")
                total_str = " ".join(total_parts)
                if total_str:
                    section7_parts.append(f"<b>Total</b>: {html.escape(total_str)}")

                remaining_parts = []
                remaining_weight_str = str(spool.get("remainingWeight") or "").strip()
                if remaining_weight_str:
                    remaining_parts.append(f"{remaining_weight_str}g")
                remaining_length_str = str(spool.get("remainingLength") or "").strip()
                if remaining_length_str:
                    remaining_parts.append(f"{remaining_length_str}mm")
                remaining_percentage_str = str(spool.get("remainingPercentage") or "").strip()
                if remaining_percentage_str:
                    remaining_parts.append(f"({remaining_percentage_str}%)")
                remaining_str = " ".join(remaining_parts)
                if remaining_str:
                    section7_parts.append(f"<b>Remaining</b>: {html.escape(remaining_str)}")

                # Section 8: note
                section8_parts = []
                note_str = str(spool.get("noteText") or "").strip()
                if note_str:
                    section8_parts.append(f"<b>Note</b>:\n<pre>{html.escape(note_str)}</pre>")

                # Build the final message by joining non-empty sections
                sections = (
                    section1_parts,
                    section2_parts,
                    section3_parts,
                    section4_parts,
                    section5_parts,
                    section6_parts,
                    section7_parts,
                    section8_parts,
                )

                return "\n\n".join("\n".join(parts) for parts in sections if parts)

        return render_emojis("{emo:attention} Spool not found")

    @override
    def select_spool(self, tool_index: str, spool_id: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/selectSpool",
            "PUT",
            json={"databaseId": spool_id, "toolIndex": tool_index, "commitCurrentSpoolValues": True},
        )

    @override
    def deselect_spool(self, tool_index: str) -> None:
        self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/selectSpool",
            "PUT",
            json={"databaseId": -1, "toolIndex": tool_index, "commitCurrentSpoolValues": True},
        )

    @override
    def get_selected_spools(self) -> dict[int, str]:
        response = self.plugin_context.api.send_request(
            f"/plugin/{self.plugin_id}/loadSpoolsByQuery?selectedPageSize=0&from=0&to=0&sortColumn=&sortOrder=&filterName=",
            timeout=15,
        )
        data = response.json()
        selections = data.get("selectedSpools", [])

        selected_spools = {}

        for tool_index, spool in enumerate(selections):
            if spool is None:
                continue

            description = self._build_spool_description(spool)
            if description:
                selected_spools[tool_index] = description

        return selected_spools
