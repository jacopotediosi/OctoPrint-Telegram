from __future__ import annotations

import html
from typing import TYPE_CHECKING

from typing_extensions import override

from ..emoji import Emoji
from ..integrations.power import POWER_PLUGINS
from ..telegram import Markup
from ..utils import StringUtils
from .base import BaseCommand, CommandContext

if TYPE_CHECKING:
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis


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

            self.plugin_context.sender.send_message(
                message,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                message_id=command_context.msg_id_to_update,
            )

            return

        if not command_context.parameter:  # Command was /power, show plugs list
            message = render_emojis("{emo:question} Which plug do you want to manage?")

            plug_buttons = []
            for plugin_handler in available_plugins:
                try:
                    for plug_data in plugin_handler.get_plugs_data():
                        label = plug_data["label"]

                        is_on = plug_data["is_on"]
                        status_emoji_name = "online" if is_on else "offline"

                        data = plug_data["data"]
                        command = (
                            command_context.cmd
                            + "_"
                            + plugin_handler.plugin_id.replace("_", "\\_")
                            + "_"
                            + str(data).replace("_", "\\_")
                        )

                        plug_buttons.append((render_emojis(f"{{emo:{status_emoji_name}}} {label}"), command))
                except Exception:
                    self._logger.exception("Caught an exception getting %s plugs", plugin_handler.plugin_id)

            max_per_row = 3
            plug_button_rows = [plug_buttons[i : i + max_per_row] for i in range(0, len(plug_buttons), max_per_row)]
            command_buttons = plug_button_rows + [[(render_emojis("{emo:cancel} Close"), "close")]]

            self.plugin_context.sender.send_message(
                message,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=command_context.msg_id_to_update,
            )

        else:
            splitted_parameters = StringUtils.split_with_escape_handling(command_context.parameter, "_")
            plugin_id, plug_data, action = (splitted_parameters + [""] * 3)[:3]

            plugin_handler = next((plugin for plugin in available_plugins if plugin.plugin_id == plugin_id), None)

            if plugin_handler is None:
                message = render_emojis(
                    f"{{emo:attention}} Plugin <code>{html.escape(plugin_id)}</code> is not available!"
                )
                command_buttons = [
                    [
                        (render_emojis("{emo:back} Back"), command_context.cmd),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ]
                ]
                self.plugin_context.sender.send_message(
                    message,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
                return

            if not action:  # Command was /power_plugin\_id_plug\_data, show plug status and ask for action
                plugs = plugin_handler.get_plugs_data()
                selected_plug = next((plug for plug in plugs if str(plug["data"]) == plug_data), None)

                if selected_plug is None:
                    message = render_emojis("{emo:attention} Selected plug not found!")
                    command_buttons = [
                        [
                            (render_emojis("{emo:back} Back"), command_context.cmd),
                            (render_emojis("{emo:cancel} Close"), "close"),
                        ]
                    ]
                    self.plugin_context.sender.send_message(
                        message,
                        chat_id=command_context.chat_id,
                        markup=Markup.HTML,
                        buttons=command_buttons,
                        message_id=command_context.msg_id_to_update,
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

                original_command = f"{command_context.cmd}_{command_context.parameter}"
                command_buttons = [
                    [
                        (render_emojis("{emo:online} Turn ON"), f"{original_command}_on"),
                        (render_emojis("{emo:offline} Turn OFF"), f"{original_command}_off"),
                    ],
                    [
                        (render_emojis("{emo:back} Back"), command_context.cmd),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ],
                ]

                self.plugin_context.sender.send_message(
                    message,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
            else:  # Command was /power_plugin\_id_plug\_data_action, execute action
                action_methods = {"on": plugin_handler.turn_on, "off": plugin_handler.turn_off}

                if action not in action_methods:
                    message = render_emojis("{emo:attention} Action not supported!")
                else:
                    try:
                        action_methods[action](plug_data)
                        message = render_emojis("{emo:check} Command sent!")
                    except Exception:
                        self._logger.exception("Caught an exception sending action to %s", plugin_id)
                        message = render_emojis("{emo:attention} Something went wrong!")

                original_command = f"{command_context.cmd}_{command_context.parameter.rsplit('_', 1)[0]}"
                command_buttons = [
                    [
                        (render_emojis("{emo:back} Back"), original_command),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ],
                ]

                self.plugin_context.sender.send_message(
                    message,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
