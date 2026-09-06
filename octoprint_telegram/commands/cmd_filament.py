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

    def __init__(self, spools: list[tuple[str, str]] | None = None, page: int = 0) -> None:
        """Set up the spools offered in the menu.

        Args:
            spools (list[tuple[str, str]], optional): The id and the description of each spool, in the order they
                are offered.
            page (int, optional): The page of the spools being shown.
        """
        self.spools = spools or []
        self.page = page


class CmdFilament(BaseCommand):
    # Number of rows of spools every page shows
    PAGE_ROWS = 15

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

        Possible callback queries, where {plugin_id} stands for the id of a filament plugin, {tool} for the
        number of a tool and {position} for the position of a spool in the page being shown:

        - /filament -> ask which filament plugin to use, or take the only one installed
        - /filament_{plugin_id} -> ask whether to show the spools of that plugin or to select one of them

        Showing spools:
        - /filament_{plugin_id}_show -> show the spools of that plugin
        - /filament_{plugin_id}_show_prevpage -> show the previous page of the spools
        - /filament_{plugin_id}_show_nextpage -> show the next page of the spools
        - /filament_{plugin_id}_show_{position} -> show the details of the spool at that position

        Selecting a spool:
        - /filament_{plugin_id}_select -> ask which tool to select a spool for, or take the only one there is
        - /filament_{plugin_id}_select_{tool} -> show the spools that tool can be given
        - /filament_{plugin_id}_select_{tool}_prevpage -> show the previous page of those spools
        - /filament_{plugin_id}_select_{tool}_nextpage -> show the next page of those spools
        - /filament_{plugin_id}_select_{tool}_{position} -> give the spool at that position to that tool,
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
            keyboard.add_grid([(plugin.plugin_name, plugin.plugin_id) for plugin in available_plugins], columns=2)
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
            choice = params[2] if len(params) > 2 else None

            if choice is None or choice in ("prevpage", "nextpage"):  # Show all spools
                if menu_state is None:
                    menu_state = FilamentMenuState()
                if choice:
                    menu_state.page += -1 if choice == "prevpage" else 1

                spools = list(plugin_handler.list_spool().items())

                keyboard = Keyboard(command_context.cmd)
                menu_state.spools, menu_state.page, total_pages = keyboard.add_entries_page(
                    [
                        ((spool_id, spool_description), spool_description, f"{plugin_handler.plugin_id}_show")
                        for spool_id, spool_description in spools
                    ],
                    menu_state.page,
                    1,
                    rows=self.PAGE_ROWS,
                    page_action_prefix=f"{plugin_handler.plugin_id}_show_",
                )
                keyboard.add_row((BACK_LABEL, plugin_handler.plugin_id))

                if spools:
                    page_str = f"    [{menu_state.page + 1} / {total_pages}]" if total_pages > 1 else ""
                    msg = render_emojis(
                        f"{{emo:info}} These are the spools available in <code>{html.escape(plugin_handler.plugin_name)}</code>.{page_str}\n"
                        "Click one for more information."
                    )
                else:
                    msg = render_emojis(
                        f"{{emo:warning}} No spool configured in plugin <code>{html.escape(plugin_handler.plugin_name)}</code>.\n"
                    )

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

            else:  # Show spool details
                menu_state = self.require_menu_state(command_context, FilamentMenuState)
                spool_id, _ = self.require_menu_chosen_item(menu_state.spools, choice)

                spool_details = plugin_handler.get_spool_details_msg(spool_id)

                msg = render_emojis(
                    f"{{emo:info}} Spool information from <code>{html.escape(plugin_handler.plugin_name)}</code>:\n\n"
                    f"{spool_details}"
                )

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row((BACK_LABEL, f"{plugin_handler.plugin_id}_show"))

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

        elif operation == "select":
            choice = params[3] if len(params) > 3 else None

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
                    columns=2,
                )
                keyboard.add_row((BACK_LABEL, plugin_handler.plugin_id))

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

                return

            if choice is None or choice in ("prevpage", "nextpage"):  # Show spool selection menu
                if menu_state is None:
                    menu_state = FilamentMenuState()
                if choice:
                    menu_state.page += -1 if choice == "prevpage" else 1

                configured_spools = list(plugin_handler.list_spool().items())
                spools = [("deselect", "Deselect"), *configured_spools]

                keyboard = Keyboard(command_context.cmd)
                menu_state.spools, menu_state.page, total_pages = keyboard.add_entries_page(
                    [
                        (
                            (spool_id, spool_description),
                            spool_description,
                            f"{plugin_handler.plugin_id}_select_{tool_index}",
                        )
                        for spool_id, spool_description in spools
                    ],
                    menu_state.page,
                    1,
                    rows=self.PAGE_ROWS,
                    page_action_prefix=f"{plugin_handler.plugin_id}_select_{tool_index}_",
                )

                back_action = f"{plugin_handler.plugin_id}_select" if has_multiple_tools else plugin_handler.plugin_id
                keyboard.add_row((BACK_LABEL, back_action))

                if configured_spools:
                    page_str = f"    [{menu_state.page + 1} / {total_pages}]" if total_pages > 1 else ""
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

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

            else:  # Select
                menu_state = self.require_menu_state(command_context, FilamentMenuState)
                spool_id, spool_title = self.require_menu_chosen_item(menu_state.spools, choice)

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
