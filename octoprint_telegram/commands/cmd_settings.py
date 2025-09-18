from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdSettings(BaseCommand):
    HEIGHT_STEPS = [10, 1, 0.1, 0.01]
    TIME_STEPS = [10, 1]

    temp_notification_settings = {}

    def execute(self, context: CommandContext):
        if context.parameter and context.parameter != "back":
            params = context.parameter.split("_")
            action = params[0]

            if action == "h":
                if len(params) > 1:
                    delta_str = params[1]
                    notification_height = self.temp_notification_settings["notification_height"]

                    if delta_str.startswith(("+", "-")):
                        new_height = max(notification_height + float(delta_str), 0)
                        self.temp_notification_settings["notification_height"] = new_height

                    else:
                        self.main._settings.set_float(["notification_height"], notification_height)
                        self.main._settings.save()

                        context.parameter = "back"
                        self.execute(context)
                        return

                msg = render_emojis(
                    "{emo:height} Set new height.\n"
                    f"Current: <b>{self.temp_notification_settings['notification_height']:.2f}mm</b>"
                )

                command_buttons = [
                    [[f"+{step}", f"{context.cmd}_h_+{step}"] for step in self.HEIGHT_STEPS],
                    [[f"-{step}", f"{context.cmd}_h_-{step}"] for step in self.HEIGHT_STEPS],
                    [
                        [render_emojis("{emo:save} Save"), f"{context.cmd}_h_s"],
                        [render_emojis("{emo:back} Back"), context.cmd],
                    ],
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
            elif action == "t":
                if len(params) > 1:
                    delta_str = params[1]
                    notification_time = self.temp_notification_settings["notification_time"]

                    if delta_str.startswith(("+", "-")):
                        new_notification_time = max(notification_time + int(delta_str), 0)
                        self.temp_notification_settings["notification_time"] = new_notification_time
                    else:
                        self.main._settings.set_int(["notification_time"], notification_time)
                        self.main._settings.save()

                        context.parameter = "back"
                        self.execute(context)
                        return

                msg = render_emojis(
                    "{emo:alarmclock} Set new time.\n"
                    f"Current: <b>{self.temp_notification_settings['notification_time']}min</b>"
                )

                command_buttons = [
                    [[f"+{step}", f"{context.cmd}_t_+{step}"] for step in self.TIME_STEPS],
                    [[f"-{step}", f"{context.cmd}_t_-{step}"] for step in self.TIME_STEPS],
                    [
                        [render_emojis("{emo:save} Save"), f"{context.cmd}_t_s"],
                        [render_emojis("{emo:back} Back"), context.cmd],
                    ],
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
        else:
            notification_height = self.main._settings.get_float(["notification_height"])
            notification_time = self.main._settings.get_int(["notification_time"])

            self.temp_notification_settings = dict(
                notification_height=notification_height, notification_time=notification_time
            )

            msg = render_emojis(
                "{emo:settings} <b>Current notification settings are:</b>\n\n"
                f"{{emo:height}} Height: {notification_height:.2f}mm\n\n"
                f"{{emo:alarmclock}} Time: {notification_time:d}min\n\n"
            )

            command_buttons = [
                [
                    [
                        render_emojis("{emo:height} Set height"),
                        f"{context.cmd}_h",
                    ],
                    [
                        render_emojis("{emo:alarmclock} Set time"),
                        f"{context.cmd}_t",
                    ],
                ],
                [[render_emojis("{emo:cancel} Close"), "close"]],
            ]
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )
