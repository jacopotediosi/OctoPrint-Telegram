from __future__ import annotations

import html
from typing import TYPE_CHECKING

from typing_extensions import override

from ..emoji import Emoji
from ..integrations.filament import FILAMENT_PLUGINS
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

if TYPE_CHECKING:
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis


class FilamentMenuState(MenuState):
    """The spools offered in the menu."""

    def __init__(self, spools: list[tuple[str, str]]) -> None:
        """Set up the spools offered in the menu.

        Args:
            spools (list[tuple[str, str]]): The id and the description of each spool, in the order they are offered.
        """
        self.spools = spools


class CmdFilament(BaseCommand):
    # Number of spools to display per page
    PAGE_SIZE = 15

    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up the command over every supported filament plugin.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        super().__init__(plugin_context)
        self.supported_plugins = [filament_plugin(plugin_context) for filament_plugin in FILAMENT_PLUGINS]

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Manage filament spools.

        Possible callback queries, where {plugin_id} stands for the id of a filament plugin, {page} for a
        page of the spool list, {tool} for the number of a tool and {position} for the position of a spool
        in the page being shown:

        - /filament -> ask which filament plugin to use, or take the only one installed
        - /filament_{plugin_id} -> ask whether to show the spools of that plugin or to select one of them

        Showing spools:
        - /filament_{plugin_id}_show -> show the first page of the spools of that plugin
        - /filament_{plugin_id}_show_{page} -> show that page of the spools of that plugin
        - /filament_{plugin_id}_show_{page}_{position} -> show the details of the spool at that position

        Selecting a spool:
        - /filament_{plugin_id}_select -> ask which tool to select a spool for, or take the only one there is
        - /filament_{plugin_id}_select_{tool} -> show the first page of the spools that tool can be given
        - /filament_{plugin_id}_select_{tool}_{page} -> show that page of the spools that tool can be given
        - /filament_{plugin_id}_select_{tool}_{page}_{position} -> give the spool at that position to that tool,
          or take away the spool given to it when the position is the one of the Deselect entry
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

            self.send_answer(command_context, msg, None, markup=Markup.HTML)

            return

        if (
            not command_context.parameter and len(available_plugins) > 1
        ):  # Command was /filament and there are multiple available plugins, show plugin selection
            msg = render_emojis("{emo:question} Please choose a filament manager plugin")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_grid(
                [(plugin.plugin_name, plugin.plugin_id) for plugin in available_plugins], buttons_per_row=2
            )
            keyboard.add_row(CLOSE_BUTTON)

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
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
                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row((BACK_LABEL, ""), CLOSE_BUTTON)

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
                return

        if len(params) < 2:  # Show operation selection
            msg = render_emojis(
                f"{{emo:question}} What do you want to do with <code>{html.escape(plugin_handler.plugin_name)}</code>?"
            )

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row(
                ("{emo:view} Show spools", f"{plugin_handler.plugin_id}_show"),
                ("{emo:pointer} Select spool", f"{plugin_handler.plugin_id}_select"),
            )
            if len(available_plugins) > 1:
                keyboard.add_row((BACK_LABEL, ""))
            else:
                keyboard.add_row(CLOSE_BUTTON)

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

            return

        menu_state = self.plugin_context.menu_states.get_menu_state(
            command_context.chat_id, command_context.msg_id_to_update, FilamentMenuState
        )
        self.send_answer(command_context, render_emojis("{emo:loading} Loading spools..."), menu_state)

        operation = params[1]

        if operation == "show":
            page_number = int(params[2]) if len(params) > 2 and params[2].isdecimal() else 0
            spool_position = params[3] if len(params) > 3 else None

            if spool_position is None:  # Show all spools
                spools = list(plugin_handler.list_spool().items())

                total_spools = len(spools)
                total_pages = max(1, (total_spools + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

                page_number = max(0, min(page_number, total_pages - 1))
                start_index = page_number * self.PAGE_SIZE
                end_index = start_index + self.PAGE_SIZE

                paginated_spools = spools[start_index:end_index]

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_grid(
                    [
                        (
                            listed_spool_description,
                            f"{plugin_handler.plugin_id}_show_{page_number}_{listed_spool_position}",
                        )
                        for listed_spool_position, (_, listed_spool_description) in enumerate(paginated_spools)
                    ],
                    buttons_per_row=1,
                )

                last_row = []
                if total_pages > 1:
                    if page_number > 0:
                        last_row.append(("{emo:up} Prev page", f"{plugin_handler.plugin_id}_show_{page_number - 1}"))
                    if page_number + 1 < total_pages:
                        last_row.append(("{emo:down} Next page", f"{plugin_handler.plugin_id}_show_{page_number + 1}"))
                last_row.append((BACK_LABEL, plugin_handler.plugin_id))
                keyboard.add_row(*last_row)

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

                self.send_answer(
                    command_context, msg, FilamentMenuState(paginated_spools), markup=Markup.HTML, keyboard=keyboard
                )

            else:  # Show spool details
                menu_state = self.require_menu_state(command_context, FilamentMenuState)
                spool_id, _ = self.require_menu_chosen_item(menu_state.spools, spool_position)

                spool_details = plugin_handler.get_spool_details_msg(spool_id)

                msg = render_emojis(
                    f"{{emo:info}} Spool information from <code>{html.escape(plugin_handler.plugin_name)}</code>:\n\n"
                    f"{spool_details}"
                )

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row((BACK_LABEL, f"{plugin_handler.plugin_id}_show_{page_number}"))

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

        elif operation == "select":
            page_number = int(params[3]) if len(params) > 3 and params[3].isdecimal() else 0
            spool_position = params[4] if len(params) > 4 else None

            printer_profile = self.plugin_context.printer_profiles.get_current_or_default()
            printer_profile_extruder = printer_profile["extruder"]
            tool_counts = printer_profile_extruder.get("count", 1)
            has_multiple_tools = tool_counts > 1

            tool_index = (
                self.require_menu_chosen_item([str(tool) for tool in range(tool_counts)], params[2])
                if len(params) > 2
                else None
            )

            if tool_index is None and not has_multiple_tools:
                tool_index = "0"

            if tool_index is None:  # Show tool selection menu
                msg = render_emojis("{emo:question} For which tool do you want to select the spool?")

                try:
                    selected_spools = plugin_handler.get_selected_spools()

                    msg += "\n\nCurrently selected spools:\n"
                    for i in range(tool_counts):
                        selected_spool = selected_spools.get(i) or "No spool selected"
                        msg += f"- Tool {html.escape(str(i))}: <code>{html.escape(selected_spool)}</code>\n"
                except Exception:
                    self._logger.exception("Caught an exception getting selected spools")

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_grid(
                    [(f"{{emo:tool}} Tool {i}", f"{plugin_handler.plugin_id}_select_{i}") for i in range(tool_counts)],
                    buttons_per_row=2,
                )
                keyboard.add_row((BACK_LABEL, plugin_handler.plugin_id))

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

                return

            if spool_position is None:  # Show spool selection menu
                configured_spools = list(plugin_handler.list_spool().items())
                spools = [("deselect", "Deselect"), *configured_spools]

                total_spools = len(spools)
                total_pages = max(1, (total_spools + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

                page_number = max(0, min(page_number, total_pages - 1))
                start_index = page_number * self.PAGE_SIZE
                end_index = start_index + self.PAGE_SIZE

                paginated_spools = spools[start_index:end_index]

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_grid(
                    [
                        (
                            listed_spool_description,
                            f"{plugin_handler.plugin_id}_select_{tool_index}_{page_number}_{listed_spool_position}",
                        )
                        for listed_spool_position, (_, listed_spool_description) in enumerate(paginated_spools)
                    ],
                    buttons_per_row=1,
                )

                last_row = []
                if total_pages > 1:
                    if page_number > 0:
                        last_row.append(
                            (
                                "{emo:up} Prev page",
                                f"{plugin_handler.plugin_id}_select_{tool_index}_{page_number - 1}",
                            )
                        )
                    if page_number + 1 < total_pages:
                        last_row.append(
                            (
                                "{emo:down} Next page",
                                f"{plugin_handler.plugin_id}_select_{tool_index}_{page_number + 1}",
                            )
                        )
                back_action = f"{plugin_handler.plugin_id}_select" if has_multiple_tools else plugin_handler.plugin_id
                last_row.append((BACK_LABEL, back_action))
                keyboard.add_row(*last_row)

                if configured_spools:
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

                self.send_answer(
                    command_context, msg, FilamentMenuState(paginated_spools), markup=Markup.HTML, keyboard=keyboard
                )

            else:  # Select
                menu_state = self.require_menu_state(command_context, FilamentMenuState)
                spool_id, spool_title = self.require_menu_chosen_item(menu_state.spools, spool_position)

                if spool_id == "deselect":
                    plugin_handler.deselect_spool(tool_index)

                    msg = render_emojis(
                        f"{{emo:check}} Successfully deselected spool for <code>Tool {html.escape(tool_index)}</code>!"
                    )
                else:
                    plugin_handler.select_spool(tool_index, spool_id)

                    msg = render_emojis(
                        f"{{emo:check}} Successfully selected spool <code>{html.escape(spool_title)}</code> for <code>Tool {html.escape(tool_index)}</code>!"
                    )

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row((BACK_LABEL, f"{plugin_handler.plugin_id}_select"))

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
