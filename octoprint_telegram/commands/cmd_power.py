from __future__ import annotations

import html
from typing import TYPE_CHECKING

from typing_extensions import override

from ..emoji import Emoji
from ..integrations.power import POWER_PLUGINS
from ..telegram import Markup, MenuState
from .base import BaseCommand, CommandContext

if TYPE_CHECKING:
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis


class PowerMenuState(MenuState):
    """The plugs offered in the menu."""

    def __init__(self, plugs: list[tuple[str, str]]) -> None:
        """Set up the plugs offered in the menu.

        Args:
            plugs (list[tuple[str, str]]): The plugin id and the plug identifier of each plug, in the order they are
                offered.
        """
        self.plugs = plugs


class CmdPower(BaseCommand):
    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up the command over every supported power plugin.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        super().__init__(plugin_context)
        self.supported_plugins = [power_plugin(plugin_context) for power_plugin in POWER_PLUGINS]

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Monitor and switch the power plugs of the installed power plugins.

        Possible callback queries, where {position} stands for the position of a plug in the list:

        - /power -> list the plugs of every installed power plugin
        - /power_{position} -> show the state of that plug and ask what to do with it
        - /power_{position}_on -> switch that plug on
        - /power_{position}_off -> switch that plug off
        """
        supported_plugins = self.supported_plugins

        available_plugins = [
            plugin_instance
            for plugin_instance in supported_plugins
            if self.plugin_context.plugins.is_enabled(plugin_instance.plugin_id)
        ]

        if not available_plugins:
            message = render_emojis(
                "{emo:warning} No power manager plugin installed. Please install one of the following plugins:\n"
            )
            for plugin_handler in supported_plugins:
                message += f"- <a href='https://plugins.octoprint.org/plugins/{html.escape(plugin_handler.plugin_id)}/'>{html.escape(plugin_handler.plugin_name)}</a>\n"

            self.update_menu(command_context, message, None, markup=Markup.HTML)

            return

        if not command_context.parameter:  # Command was /power, show plugs list
            message = render_emojis("{emo:question} Which plug do you want to manage?")

            plugs = []
            plug_buttons = []
            for plugin_handler in available_plugins:
                try:
                    for plug_data in plugin_handler.get_plugs_data():
                        label = plug_data["label"]

                        is_on = plug_data["is_on"]
                        status_emoji_name = "online" if is_on else "offline"

                        plugs.append((plugin_handler.plugin_id, str(plug_data["data"])))

                        plug_buttons.append(
                            (
                                render_emojis(f"{{emo:{status_emoji_name}}} {label}"),
                                f"{command_context.cmd}_{len(plugs) - 1}",
                            )
                        )
                except Exception:
                    self._logger.exception("Caught an exception getting %s plugs", plugin_handler.plugin_id)

            max_per_row = 3
            plug_button_rows = [plug_buttons[i : i + max_per_row] for i in range(0, len(plug_buttons), max_per_row)]
            command_buttons = plug_button_rows + [[(render_emojis("{emo:cancel} Close"), "close")]]

            self.update_menu(
                command_context, message, PowerMenuState(plugs), markup=Markup.HTML, buttons=command_buttons
            )

        else:
            params = command_context.parameter.split("_")
            plug_index, action = (params + [""] * 2)[:2]

            menu_state = self.require_menu_state(command_context, PowerMenuState)

            command_buttons = [
                [
                    (render_emojis("{emo:back} Back"), command_context.cmd),
                    (render_emojis("{emo:cancel} Close"), "close"),
                ]
            ]

            if not (plug_index.isdigit() and int(plug_index) < len(menu_state.plugs)):
                self.update_menu(
                    command_context,
                    render_emojis("{emo:attention} Selected plug not found!"),
                    None,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                )
                return

            plugin_id, plug = menu_state.plugs[int(plug_index)]

            plugin_handler = next((plugin for plugin in available_plugins if plugin.plugin_id == plugin_id), None)

            if plugin_handler is None:
                message = render_emojis(
                    f"{{emo:attention}} Plugin <code>{html.escape(plugin_id)}</code> is not available!"
                )
                self.update_menu(command_context, message, None, markup=Markup.HTML, buttons=command_buttons)
                return

            if not action:  # Command was /power_plugIndex, show plug status and ask for action
                plugs = plugin_handler.get_plugs_data()
                selected_plug = next((p for p in plugs if str(p["data"]) == plug), None)

                if selected_plug is None:
                    self.update_menu(
                        command_context,
                        render_emojis("{emo:attention} Selected plug not found!"),
                        None,
                        markup=Markup.HTML,
                        buttons=command_buttons,
                    )
                    return

                label = selected_plug["label"]
                is_on = selected_plug["is_on"]
                status_text = "ON" if is_on else "OFF"
                status_emoji_name = "online" if is_on else "offline"

                message = render_emojis(
                    f"{{emo:info}} Plug <code>{html.escape(label)}</code> is {{emo:{status_emoji_name}}} {status_text}.\n"
                    "{emo:question} What do you want to do?"
                )

                command_buttons = [
                    [
                        (render_emojis("{emo:online} Turn ON"), f"{command_context.cmd}_{plug_index}_on"),
                        (render_emojis("{emo:offline} Turn OFF"), f"{command_context.cmd}_{plug_index}_off"),
                    ],
                    [
                        (render_emojis("{emo:back} Back"), command_context.cmd),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ],
                ]

                self.update_menu(command_context, message, menu_state, markup=Markup.HTML, buttons=command_buttons)
            else:  # Command was /power_plugIndex_action, execute action
                action_methods = {"on": plugin_handler.turn_on, "off": plugin_handler.turn_off}

                if action not in action_methods:
                    message = render_emojis("{emo:attention} Action not supported!")
                else:
                    try:
                        action_methods[action](plug)
                        message = render_emojis("{emo:check} Command sent!")
                    except Exception:
                        self._logger.exception("Caught an exception sending action to %s", plugin_id)
                        message = render_emojis("{emo:attention} Something went wrong!")

                command_buttons = [
                    [
                        (render_emojis("{emo:back} Back"), f"{command_context.cmd}_{plug_index}"),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ],
                ]

                self.update_menu(command_context, message, menu_state, markup=Markup.HTML, buttons=command_buttons)
