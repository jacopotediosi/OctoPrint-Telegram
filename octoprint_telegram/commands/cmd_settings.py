from __future__ import annotations

from typing import ClassVar

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdSettings(BaseCommand):
    HEIGHT_STEPS: ClassVar[list[float]] = [10, 1, 0.1, 0.01]
    TIME_STEPS: ClassVar[list[int]] = [10, 1]

    _temp_notification_settings: ClassVar[dict[str, float]] = {}

    def execute(self, command_context: CommandContext) -> None:
        if command_context.parameter and command_context.parameter != "back":
            params = command_context.parameter.split("_")
            action = params[0]

            if action == "h":
                if len(params) > 1:
                    delta_str = params[1]
                    notification_height = self._temp_notification_settings["notification_height"]

                    if delta_str.startswith(("+", "-")):
                        new_height = max(notification_height + float(delta_str), 0)
                        self._temp_notification_settings["notification_height"] = new_height

                    else:
                        self.plugin_context.settings.notification_height = notification_height
                        self.plugin_context.settings.save()

                        command_context.parameter = "back"
                        self.execute(command_context)
                        return

                msg = render_emojis(
                    "{emo:height} Set new height.\n"
                    f"Current: <b>{self._temp_notification_settings['notification_height']:.2f}mm</b>"
                )

                command_buttons = [
                    [(f"+{step}", f"{command_context.cmd}_h_+{step}") for step in self.HEIGHT_STEPS],
                    [(f"-{step}", f"{command_context.cmd}_h_-{step}") for step in self.HEIGHT_STEPS],
                    [
                        (render_emojis("{emo:save} Save"), f"{command_context.cmd}_h_s"),
                        (render_emojis("{emo:back} Back"), command_context.cmd),
                    ],
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
            elif action == "t":
                if len(params) > 1:
                    delta_str = params[1]
                    notification_time = self._temp_notification_settings["notification_time"]

                    if delta_str.startswith(("+", "-")):
                        new_notification_time = max(notification_time + int(delta_str), 0)
                        self._temp_notification_settings["notification_time"] = new_notification_time
                    else:
                        self.plugin_context.settings.notification_time = int(notification_time)
                        self.plugin_context.settings.save()

                        command_context.parameter = "back"
                        self.execute(command_context)
                        return

                msg = render_emojis(
                    "{emo:alarmclock} Set new time.\n"
                    f"Current: <b>{self._temp_notification_settings['notification_time']}min</b>"
                )

                command_buttons = [
                    [(f"+{step}", f"{command_context.cmd}_t_+{step}") for step in self.TIME_STEPS],
                    [(f"-{step}", f"{command_context.cmd}_t_-{step}") for step in self.TIME_STEPS],
                    [
                        (render_emojis("{emo:save} Save"), f"{command_context.cmd}_t_s"),
                        (render_emojis("{emo:back} Back"), command_context.cmd),
                    ],
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
        else:
            notification_height = self.plugin_context.settings.notification_height
            notification_time = self.plugin_context.settings.notification_time

            self._temp_notification_settings.update(
                {
                    "notification_height": notification_height,
                    "notification_time": notification_time,
                }
            )

            msg = render_emojis(
                "{emo:settings} <b>Current notification settings are:</b>\n\n"
                f"{{emo:height}} Height: {notification_height:.2f}mm\n\n"
                f"{{emo:alarmclock}} Time: {notification_time:d}min\n\n"
            )

            command_buttons = [
                [
                    (
                        render_emojis("{emo:height} Set height"),
                        f"{command_context.cmd}_h",
                    ),
                    (
                        render_emojis("{emo:alarmclock} Set time"),
                        f"{command_context.cmd}_t",
                    ),
                ],
                [(render_emojis("{emo:cancel} Close"), "close")],
            ]
            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=command_context.msg_id_to_update,
            )
