import html
from abc import ABC, abstractmethod

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdFilament(BaseCommand):
    # Number of spools to display per page
    PAGE_SIZE = 15

    def execute(self, context: CommandContext):
        """
        Possible callback queries:

        Entry points:
        - /filament -> ask which pluginid or automatically select if there is only one
        - /filament_pluginid -> ask for which operation (show/select)

        Show:
        - /filament_pluginid_show -> user is browsing spools at page 0
        - /filament_pluginid_show_page -> user is browsing spools at certain page
        - /filament_pluginid_show_page_id -> show details of spool by id

        Select:
        - /filament_pluginid_select -> ask for which tool or automatically select if there is only one
        - /filament_pluginid_select_tool -> user is selecting spools at page 0
        - /filament_pluginid_select_tool_page -> user is selecting spools at certain page
        - /filament_pluginid_select_tool_page_id -> user has selected spool by id
        """

        supported_plugins = [
            self.FilamentManagerFilamentPlugin(self),
            self.SpoolmanFilamentPlugin(self),
            self.SpoolManagerFilamentPlugin(self),
        ]

        available_plugins = [
            plugin_instance
            for plugin_instance in supported_plugins
            if self.main._plugin_manager.get_plugin(plugin_instance.plugin_id, True)
        ]

        if not available_plugins:
            msg = f"{get_emoji('warning')} No filament plugin installed. Please install one of the following plugins:\n"
            for plugin_handler in supported_plugins:
                msg += f"- <a href='https://plugins.octoprint.org/plugins/{html.escape(plugin_handler.plugin_id)}/'>{html.escape(plugin_handler.plugin_name)}</a>\n"

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )

            return

        if (
            not context.parameter and len(available_plugins) > 1
        ):  # Command was /filament and there are multiple available plugins, show plugin selection
            msg = f"{get_emoji('question')} Please choose a filament manager plugin"

            command_buttons = []
            for i in range(0, len(available_plugins), 2):
                row = []
                for plugin in available_plugins[i : i + 2]:
                    row.append([f"{plugin.plugin_name}", f"{context.cmd}_{plugin.plugin_id}"])
                command_buttons.append(row)
            command_buttons.append([[f"{get_emoji('cancel')} Close", "close"]])

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )
            return

        params = context.parameter.split("_")

        # Determine plugin handler
        if not context.parameter:  # If params are missing plugin_id, select the first plugin available
            plugin_handler = available_plugins[0]
        else:  # Search the plugin by its id specified in params
            plugin_id = params[0]

            plugin_handler = next((plugin for plugin in available_plugins if plugin.plugin_id == plugin_id), None)

            if plugin_handler is None:
                msg = f"{get_emoji('attention')} Plugin <code>{html.escape(plugin_id)}</code> is not available!"
                command_buttons = [
                    [[f"{get_emoji('back')} Back", context.cmd], [f"{get_emoji('cancel')} Close", "close"]]
                ]
                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
                return

        if len(params) < 2:  # Show operation selection
            msg = f"{get_emoji('question')} What do you want to do with <code>{html.escape(plugin_handler.plugin_name)}</code>?"

            command_buttons = [
                [
                    [f"{get_emoji('view')} Show spools", f"{context.cmd}_{plugin_handler.plugin_id}_show"],
                    [f"{get_emoji('pointer')} Select spool", f"{context.cmd}_{plugin_handler.plugin_id}_select"],
                ]
            ]
            if len(available_plugins) > 1:
                command_buttons.append([[f"{get_emoji('back')} Back", f"{context.cmd}"]])
            else:
                command_buttons.append([[f"{get_emoji('cancel')} Close", "close"]])

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

            return

        self.main.send_msg(
            f"{get_emoji('loading')} Loading spools...",
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )

        operation = params[1]

        if operation == "show":
            page_number = int(params[2] or 0) if len(params) > 2 else 0
            spool_id = params[3] if len(params) > 3 else None

            if spool_id is None:  # Show all spools
                spools = list(plugin_handler.list_spool().items())

                total_spools = len(spools)
                total_pages = max(1, (total_spools + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

                page_number = max(0, min(page_number, total_pages - 1))
                start_index = page_number * self.PAGE_SIZE
                end_index = start_index + self.PAGE_SIZE

                paginated_spools = spools[start_index:end_index]

                spool_buttons = []
                for spool_id, spool_desc in paginated_spools:
                    spool_buttons.append(
                        [[spool_desc, f"{context.cmd}_{plugin_handler.plugin_id}_show_{page_number}_{spool_id}"]]
                    )

                last_row = []
                if total_pages > 1:
                    if page_number > 0:
                        last_row.append(
                            [
                                f"{get_emoji('up')} Prev page",
                                f"{context.cmd}_{plugin_handler.plugin_id}_show_{page_number - 1}",
                            ]
                        )
                    if page_number + 1 < total_pages:
                        last_row.append(
                            [
                                f"{get_emoji('down')} Next page",
                                f"{context.cmd}_{plugin_handler.plugin_id}_show_{page_number + 1}",
                            ]
                        )
                last_row.append([f"{get_emoji('back')} Back", f"{context.cmd}_{plugin_handler.plugin_id}"])

                command_buttons = spool_buttons + [last_row]

                if spools:
                    page_str = f"    [{page_number + 1} / {total_pages}]" if total_pages > 1 else ""
                    msg = (
                        f"{get_emoji('info')} These are the spools available in <code>{html.escape(plugin_handler.plugin_name)}</code>.{page_str}\n"
                        "Click one for more information."
                    )
                else:
                    msg = f"{get_emoji('warning')} No spool configured in plugin <code>{html.escape(plugin_handler.plugin_name)}</code>.\n"

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

            else:  # Show spool details
                spool_details = plugin_handler.get_spool_details_msg(spool_id)

                msg = (
                    f"{get_emoji('info')} Spool information from <code>{html.escape(plugin_handler.plugin_name)}</code>:\n\n"
                    f"{spool_details}"
                )

                command_buttons = [
                    [[f"{get_emoji('back')} Back", f"{context.cmd}_{plugin_handler.plugin_id}_show_{page_number}"]]
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

        elif operation == "select":
            tool_index = params[2] if len(params) > 2 else None
            page_number = int(params[3] or 0) if len(params) > 3 else 0
            spool_id = params[4] if len(params) > 4 else None

            if tool_index is None:  # Show tool selection menu
                printer_profile = self.main._printer_profile_manager.get_current()
                printer_profile_extruder = printer_profile["extruder"]
                tool_counts = printer_profile_extruder.get("count", 1)

                msg = f"{get_emoji('question')} For which tool do you want to select the spool?"

                try:
                    selected_spools = plugin_handler.get_selected_spools()

                    msg += "\n\nCurrently selected spools:\n"
                    for i in range(tool_counts):
                        selected_spool = selected_spools.get(i) or "No spool selected"
                        msg += f"- Tool {html.escape(str(i))}: <code>{html.escape(selected_spool)}</code>\n"
                except Exception:
                    self._logger.exception("Caught an exception getting selected spools")

                command_buttons = [
                    [
                        [f"{get_emoji('tool')} Tool {i}", f"{context.cmd}_{plugin_handler.plugin_id}_select_{i}"]
                        for i in range(j, min(j + 2, tool_counts))
                    ]
                    for j in range(0, tool_counts, 2)
                ]
                command_buttons.append([[f"{get_emoji('back')} Back", f"{context.cmd}_{plugin_handler.plugin_id}"]])

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

                return

            if spool_id is None:  # Show spool selection menu
                spools = [("deselect", "Deselect")] + list(plugin_handler.list_spool().items())

                total_spools = len(spools)
                total_pages = max(1, (total_spools + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

                page_number = max(0, min(page_number, total_pages - 1))
                start_index = page_number * self.PAGE_SIZE
                end_index = start_index + self.PAGE_SIZE

                paginated_spools = spools[start_index:end_index]

                spool_buttons = []
                for spool_id, spool_desc in paginated_spools:
                    spool_buttons.append(
                        [
                            [
                                spool_desc,
                                f"{context.cmd}_{plugin_handler.plugin_id}_select_{tool_index}_{page_number}_{spool_id}",
                            ]
                        ]
                    )

                last_row = []
                if total_pages > 1:
                    if page_number > 0:
                        last_row.append(
                            [
                                f"{get_emoji('up')} Prev page",
                                f"{context.cmd}_{plugin_handler.plugin_id}_select_{tool_index}_{page_number - 1}",
                            ]
                        )
                    if page_number + 1 < total_pages:
                        last_row.append(
                            [
                                f"{get_emoji('down')} Next page",
                                f"{context.cmd}_{plugin_handler.plugin_id}_select_{tool_index}_{page_number + 1}",
                            ]
                        )
                last_row.append([f"{get_emoji('back')} Back", f"{context.cmd}_{plugin_handler.plugin_id}_select"])

                command_buttons = []
                command_buttons.extend(spool_buttons)
                command_buttons.append(last_row)

                if spools:
                    page_str = f"    [{page_number + 1} / {total_pages}]" if total_pages > 1 else ""
                    msg = f"{get_emoji('question')} Which spool do you want to select for <code>Tool {html.escape(tool_index)}</code>? {page_str}"
                    try:
                        selected_spools = plugin_handler.get_selected_spools()
                        selected_spool = selected_spools.get(int(tool_index)) or "No spool selected"
                        msg += f"\n\nCurrently selected: <code>{html.escape(selected_spool)}</code>."
                    except Exception:
                        self._logger.exception("Caught an exception getting selected spools")
                else:
                    msg = f"{get_emoji('warning')} No spool configured in plugin <code>{html.escape(plugin_handler.plugin_name)}</code>.\n"

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

            else:  # Select
                if spool_id == "deselect":
                    plugin_handler.deselect_spool(tool_index)

                    msg = f"{get_emoji('check')} Successfully deselected spool for <code>Tool {html.escape(tool_index)}</code>!"
                else:
                    plugin_handler.select_spool(tool_index, spool_id)

                    spool_title = plugin_handler.list_spool()[spool_id]
                    msg = f"{get_emoji('check')} Successfully selected spool <code>{html.escape(spool_title)}</code> for <code>Tool {html.escape(tool_index)}</code>!"

                command_buttons = [[[f"{get_emoji('back')} Back", f"{context.cmd}_{plugin_handler.plugin_id}_select"]]]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

    class FilamentPlugin(ABC):
        def __init__(self, parent: "CmdFilament"):
            self.parent = parent

        @property
        @abstractmethod
        def plugin_id(self):
            pass

        @property
        @abstractmethod
        def plugin_name(self):
            pass

        @abstractmethod
        def list_spool(self):
            """
            Retrieve a mapping of spool IDs to their human-readable descriptions.

            Returns:
                dict: A dictionary mapping spool IDs to their short descriptions.

                      Each description follows the format: "Name Material Color (Vendor) [Remaining g]"

            Example:
                >>> plugin.list_spool()
                {
                    "1": "PLA+ Red (Prusament) [850g]",
                    "2": "PETG Green (SUNLU) [150g]",
                    "3": "TPU Black (eSUN) [450g]"
                }
            """
            pass

        @abstractmethod
        def get_spool_details_msg(self, spool_id):
            """
            Retrieve detailed information for a specific spool and format it as HTML message.

            Args:
                spool_id: The ID of the spool to retrieve details for.

            Returns:
                str: HTML-formatted string containing spool details like (depends on the specific plugin)
                    ID, name, vendor, material, color, cost, density, diameter, weight information, etc.

            Example:
                >>> plugin.get_spool_details_msg(1)
                '<b>ID</b>: 1\\n'
                '<b>Name</b>: Spool1\\n'
                '<b>Vendor</b>: Sunlu\\n'
                '<b>Material</b>: ABS\\n\\n'
                '<b>Cost</b>: 20.0\\n'
                '<b>Density</b>: 1.25\\n'
                '<b>Diameter</b>: 1.75\\n\\n'
                '<b>Total weight</b>: 1000g\\n'
                '<b>Used</b>: 300g\\n'
                '<b>Remaining</b>: 700g (70%)\\n'
            """
            pass

        @abstractmethod
        def select_spool(self, tool_index, spool_id):
            pass

        @abstractmethod
        def deselect_spool(self, tool_index):
            pass

        @abstractmethod
        def get_selected_spools(self):
            """
            Retrieve a mapping of tool numbers to their currently selected spool human-readable descriptions.

            Returns:
            dict: A dictionary mapping tool numbers to their short spool descriptions.

                    Each description follows the format: "Name Material Color (Vendor) [Remaining g]"

            Example:
            >>> plugin.get_selected_spools()
            {
                0: "PLA+ Red (Prusament) [850g]",
                1: "PETG Green (SUNLU) [150g]",
                2: "TPU Black (eSUN) [450g]"
            }
            """
            pass

    class FilamentManagerFilamentPlugin(FilamentPlugin):
        @property
        def plugin_id(self):
            return "filamentmanager"

        @property
        def plugin_name(self):
            return "FilamentManager"

        def _build_spool_description(self, spool):
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

        def list_spool(self):
            response = self.parent.main.send_octoprint_request(f"/plugin/{self.plugin_id}/spools", timeout=15)
            data = response.json()

            spool_dict = {}
            for spool in data.get("spools", []):
                spool_id = str(spool.get("id"))

                description = self._build_spool_description(spool)
                if description:
                    spool_dict[spool_id] = description

            return spool_dict

        def get_spool_details_msg(self, spool_id):
            response = self.parent.main.send_octoprint_request(
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

        def select_spool(self, tool_index, spool_id):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/selections/{tool_index}",
                "PATCH",
                json={"selection": {"tool": tool_index, "spool": {"id": spool_id}, "updateui": True}},
            )

        def deselect_spool(self, tool_index):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/selections/{tool_index}",
                "PATCH",
                json={"selection": {"tool": tool_index, "spool": {"id": None}, "updateui": True}},
            )

        def get_selected_spools(self):
            response = self.parent.main.send_octoprint_request(
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

    class SpoolmanFilamentPlugin(FilamentPlugin):
        @property
        def plugin_id(self):
            return "Spoolman"

        @property
        def plugin_name(self):
            return "Spoolman"

        def _build_spool_description(self, spool):
            filament = spool.get("filament", {})
            vendor = filament.get("vendor", {})

            parts = [
                filament.get("name"),
                filament.get("material"),
                f"({vendor['name']})" if vendor.get("name") else None,
                f"[{spool['remaining_weight']}g]" if spool.get("remaining_weight") is not None else None,
            ]

            return " ".join(filter(None, parts))

        def list_spool(self):
            response = self.parent.main.send_octoprint_request(f"/plugin/{self.plugin_id}/spoolman/spools", timeout=15)
            data = response.json().get("data", {})

            spool_dict = {}
            for spool in data.get("spools", []):
                spool_id = str(spool.get("id"))

                description = self._build_spool_description(spool)
                if description:
                    spool_dict[spool_id] = description

            return spool_dict

        def get_spool_details_msg(self, spool_id):
            response = self.parent.main.send_octoprint_request(
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

            return f"{get_emoji('attention')} Spool not found"

        def select_spool(self, tool_index, spool_id):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/self/spool",
                "POST",
                json={"spoolId": spool_id, "toolIdx": tool_index},
            )

        def deselect_spool(self, tool_index):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/self/spool",
                "POST",
                json={"toolIdx": tool_index},
            )

        def get_selected_spools(self):
            response = self.parent.main.send_octoprint_request(f"/plugin/{self.plugin_id}/spoolman/spools", timeout=15)
            spools = response.json().get("data", {}).get("spools", [])

            selected_spools_config = self.parent.main._settings.global_get(
                ["plugins", self.plugin_id, "selectedSpoolIds"]
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

    class SpoolManagerFilamentPlugin(FilamentPlugin):
        @property
        def plugin_id(self):
            return "SpoolManager"

        @property
        def plugin_name(self):
            return "SpoolManager"

        def _build_spool_description(self, spool):
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

        def list_spool(self):
            response = self.parent.main.send_octoprint_request(
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

        def get_spool_details_msg(self, spool_id):
            response = self.parent.main.send_octoprint_request(
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
                        section4_parts.append(
                            f"<b>Flowrate compensation</b>: {html.escape(flowrate_compensation_str)}%"
                        )

                    # Section 5: density, diameter
                    section5_parts = []
                    density_str = str(spool.get("density") or "").strip()
                    if density_str:
                        section5_parts.append(f"<b>Density</b>: {html.escape(density_str)}g/cm&#179;")
                    diameter_str = str(spool.get("diameter") or "").strip()
                    diameter_tolerance_str = str(spool.get("diameterTolerance") or "").strip()
                    if diameter_str:
                        tolerance_part = (
                            f" &#177;{html.escape(diameter_tolerance_str)}" if diameter_tolerance_str else ""
                        )
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
                    if section8_parts:
                        sections.append("\n".join(section8_parts))

                    return "\n\n".join(sections)

            return f"{get_emoji('attention')} Spool not found"

        def select_spool(self, tool_index, spool_id):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/selectSpool", "PUT", json={"databaseId": spool_id, "toolIndex": tool_index}
            )

        def deselect_spool(self, tool_index):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/selectSpool", "PUT", json={"databaseId": -1, "toolIndex": tool_index}
            )

        def get_selected_spools(self):
            response = self.parent.main.send_octoprint_request(
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
