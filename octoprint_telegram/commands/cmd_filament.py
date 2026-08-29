import html

from ..emoji import Emoji
from ..integrations.filament import FILAMENT_PLUGINS
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdFilament(BaseCommand):
    # Number of spools to display per page
    PAGE_SIZE = 15

    def __init__(self, plugin_context):
        super().__init__(plugin_context)
        self.supported_plugins = [filament_plugin(plugin_context) for filament_plugin in FILAMENT_PLUGINS]

    def execute(self, command_context: CommandContext):
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

        supported_plugins = self.supported_plugins

        available_plugins = [
            plugin_instance
            for plugin_instance in supported_plugins
            if self.plugin_context.plugins.is_enabled(plugin_instance.plugin_id)
        ]

        if not available_plugins:
            msg = render_emojis(
                "{emo:warning} No filament plugin installed. Please install one of the following plugins:\n"
            )
            for plugin_handler in supported_plugins:
                msg += f"- <a href='https://plugins.octoprint.org/plugins/{html.escape(plugin_handler.plugin_id)}/'>{html.escape(plugin_handler.plugin_name)}</a>\n"

            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                message_id=command_context.msg_id_to_update,
            )

            return

        if (
            not command_context.parameter and len(available_plugins) > 1
        ):  # Command was /filament and there are multiple available plugins, show plugin selection
            msg = render_emojis("{emo:question} Please choose a filament manager plugin")

            command_buttons = []
            for i in range(0, len(available_plugins), 2):
                row = []
                for plugin in available_plugins[i : i + 2]:
                    row.append((f"{plugin.plugin_name}", f"{command_context.cmd}_{plugin.plugin_id}"))
                command_buttons.append(row)
            command_buttons.append([(render_emojis("{emo:cancel} Close"), "close")])

            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=command_context.msg_id_to_update,
            )
            return

        params = command_context.parameter.split("_")

        # Determine plugin handler
        if not command_context.parameter:  # If params are missing plugin_id, select the first plugin available
            plugin_handler = available_plugins[0]
        else:  # Search the plugin by its id specified in params
            plugin_id = params[0]

            plugin_handler = next((plugin for plugin in available_plugins if plugin.plugin_id == plugin_id), None)

            if plugin_handler is None:
                msg = render_emojis(f"{{emo:attention}} Plugin <code>{html.escape(plugin_id)}</code> is not available!")
                command_buttons = [
                    [
                        (render_emojis("{emo:back} Back"), command_context.cmd),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ]
                ]
                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
                return

        if len(params) < 2:  # Show operation selection
            msg = render_emojis(
                f"{{emo:question}} What do you want to do with <code>{html.escape(plugin_handler.plugin_name)}</code>?"
            )

            command_buttons = [
                [
                    (render_emojis("{emo:view} Show spools"), f"{command_context.cmd}_{plugin_handler.plugin_id}_show"),
                    (
                        render_emojis("{emo:pointer} Select spool"),
                        f"{command_context.cmd}_{plugin_handler.plugin_id}_select",
                    ),
                ]
            ]
            if len(available_plugins) > 1:
                command_buttons.append([(render_emojis("{emo:back} Back"), f"{command_context.cmd}")])
            else:
                command_buttons.append([(render_emojis("{emo:cancel} Close"), "close")])

            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=command_context.msg_id_to_update,
            )

            return

        self.plugin_context.sender.send_message(
            render_emojis("{emo:loading} Loading spools..."),
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
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
                        [
                            (
                                spool_desc,
                                f"{command_context.cmd}_{plugin_handler.plugin_id}_show_{page_number}_{spool_id}",
                            )
                        ]
                    )

                last_row = []
                if total_pages > 1:
                    if page_number > 0:
                        last_row.append(
                            (
                                render_emojis("{emo:up} Prev page"),
                                f"{command_context.cmd}_{plugin_handler.plugin_id}_show_{page_number - 1}",
                            )
                        )
                    if page_number + 1 < total_pages:
                        last_row.append(
                            (
                                render_emojis("{emo:down} Next page"),
                                f"{command_context.cmd}_{plugin_handler.plugin_id}_show_{page_number + 1}",
                            )
                        )
                last_row.append((render_emojis("{emo:back} Back"), f"{command_context.cmd}_{plugin_handler.plugin_id}"))

                command_buttons = spool_buttons + [last_row]

                if spools:
                    page_str = f"    [{page_number + 1} / {total_pages}]" if total_pages > 1 else ""
                    msg = render_emojis(
                        f"{{emo:info}} These are the spools available in <code>{html.escape(plugin_handler.plugin_name)}</code>.{page_str}\n"
                        "Click one for more information."
                    )
                else:
                    msg = render_emojis(
                        f"{{emo:warning}} No spool configured in plugin <code>{html.escape(plugin_handler.plugin_name)}</code>.\n"
                    )

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )

            else:  # Show spool details
                spool_details = plugin_handler.get_spool_details_msg(spool_id)

                msg = render_emojis(
                    f"{{emo:info}} Spool information from <code>{html.escape(plugin_handler.plugin_name)}</code>:\n\n"
                    f"{spool_details}"
                )

                command_buttons = [
                    [
                        (
                            render_emojis("{emo:back} Back"),
                            f"{command_context.cmd}_{plugin_handler.plugin_id}_show_{page_number}",
                        )
                    ]
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )

        elif operation == "select":
            tool_index = params[2] if len(params) > 2 else None
            page_number = int(params[3] or 0) if len(params) > 3 else 0
            spool_id = params[4] if len(params) > 4 else None

            if tool_index is None:  # Show tool selection menu
                printer_profile = self.plugin_context.printer_profiles.get_current()
                printer_profile_extruder = printer_profile["extruder"]
                tool_counts = printer_profile_extruder.get("count", 1)

                msg = render_emojis("{emo:question} For which tool do you want to select the spool?")

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
                        (
                            render_emojis(f"{{emo:tool}} Tool {i}"),
                            f"{command_context.cmd}_{plugin_handler.plugin_id}_select_{i}",
                        )
                        for i in range(j, min(j + 2, tool_counts))
                    ]
                    for j in range(0, tool_counts, 2)
                ]
                command_buttons.append(
                    [(render_emojis("{emo:back} Back"), f"{command_context.cmd}_{plugin_handler.plugin_id}")]
                )

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
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
                            (
                                spool_desc,
                                f"{command_context.cmd}_{plugin_handler.plugin_id}_select_{tool_index}_{page_number}_{spool_id}",
                            )
                        ]
                    )

                last_row = []
                if total_pages > 1:
                    if page_number > 0:
                        last_row.append(
                            (
                                render_emojis("{emo:up} Prev page"),
                                f"{command_context.cmd}_{plugin_handler.plugin_id}_select_{tool_index}_{page_number - 1}",
                            )
                        )
                    if page_number + 1 < total_pages:
                        last_row.append(
                            (
                                render_emojis("{emo:down} Next page"),
                                f"{command_context.cmd}_{plugin_handler.plugin_id}_select_{tool_index}_{page_number + 1}",
                            )
                        )
                last_row.append(
                    (render_emojis("{emo:back} Back"), f"{command_context.cmd}_{plugin_handler.plugin_id}_select")
                )

                command_buttons = []
                command_buttons.extend(spool_buttons)
                command_buttons.append(last_row)

                if spools:
                    page_str = f"    [{page_number + 1} / {total_pages}]" if total_pages > 1 else ""
                    msg = render_emojis(
                        f"{{emo:question}} Which spool do you want to select for <code>Tool {html.escape(tool_index)}</code>? {page_str}"
                    )
                    try:
                        selected_spools = plugin_handler.get_selected_spools()
                        selected_spool = selected_spools.get(int(tool_index)) or "No spool selected"
                        msg += f"\n\nCurrently selected: <code>{html.escape(selected_spool)}</code>."
                    except Exception:
                        self._logger.exception("Caught an exception getting selected spools")
                else:
                    msg = render_emojis(
                        f"{{emo:warning}} No spool configured in plugin <code>{html.escape(plugin_handler.plugin_name)}</code>.\n"
                    )

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )

            else:  # Select
                if spool_id == "deselect":
                    plugin_handler.deselect_spool(tool_index)

                    msg = render_emojis(
                        f"{{emo:check}} Successfully deselected spool for <code>Tool {html.escape(tool_index)}</code>!"
                    )
                else:
                    plugin_handler.select_spool(tool_index, spool_id)

                    spool_title = plugin_handler.list_spool()[spool_id]
                    msg = render_emojis(
                        f"{{emo:check}} Successfully selected spool <code>{html.escape(spool_title)}</code> for <code>Tool {html.escape(tool_index)}</code>!"
                    )

                command_buttons = [
                    [(render_emojis("{emo:back} Back"), f"{command_context.cmd}_{plugin_handler.plugin_id}_select")]
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
