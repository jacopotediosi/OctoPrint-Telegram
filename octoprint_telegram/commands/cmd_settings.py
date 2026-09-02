from __future__ import annotations

from typing import ClassVar

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class SettingsMenuState(MenuState):
    """The settings being edited."""

    def __init__(self, notification_height: float, notification_time: int) -> None:
        """Set up the settings being edited.

        Args:
            notification_height (float): The increase in Z height that triggers a progress notification.
            notification_time (int): The minutes between progress notifications.
        """
        self.notification_height = notification_height
        self.notification_time = notification_time


class CmdSettings(BaseCommand):
    HEIGHT_STEPS: ClassVar[list[float]] = [10, 1, 0.1, 0.01]
    TIME_STEPS: ClassVar[list[int]] = [10, 1]

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Show and change the notification settings.

        Possible callback queries, where {step} stands for one of the increments offered by the menu:

        - /settings -> show the current notification settings
        - /settings_height -> show the height being edited
        - /settings_height_+{step} -> raise the height being edited
        - /settings_height_-{step} -> lower the height being edited
        - /settings_height_save -> store the height being edited in the plugin settings
        - /settings_time -> show the time being edited
        - /settings_time_+{step} -> raise the time being edited
        - /settings_time_-{step} -> lower the time being edited
        - /settings_time_save -> store the time being edited in the plugin settings
        """
        if not command_context.parameter:
            self._settings_menu(command_context)
            return

        setting, _, value = command_context.parameter.partition("_")

        menu_state = (
            self.require_menu_state(command_context, SettingsMenuState)
            if value
            else SettingsMenuState(
                self.plugin_context.settings.notification_height,
                self.plugin_context.settings.notification_time,
            )
        )

        if setting == "height":
            if value:
                if value.startswith(("+", "-")):
                    menu_state.notification_height = max(menu_state.notification_height + float(value), 0)
                else:
                    self.plugin_context.settings.notification_height = menu_state.notification_height
                    self.plugin_context.settings.save()

                    self._settings_menu(command_context)
                    return

            msg = render_emojis(
                f"{{emo:height}} Set new height.\nCurrent: <b>{menu_state.notification_height:.2f}mm</b>"
            )

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row(*((f"+{step}", f"height_+{step}") for step in self.HEIGHT_STEPS))
            keyboard.add_row(*((f"-{step}", f"height_-{step}") for step in self.HEIGHT_STEPS))
            keyboard.add_row(("{emo:save} Save", "height_save"), (BACK_LABEL, ""))

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
        elif setting == "time":
            if value:
                if value.startswith(("+", "-")):
                    menu_state.notification_time = max(menu_state.notification_time + int(value), 0)
                else:
                    self.plugin_context.settings.notification_time = menu_state.notification_time
                    self.plugin_context.settings.save()

                    self._settings_menu(command_context)
                    return

            msg = render_emojis(f"{{emo:alarmclock}} Set new time.\nCurrent: <b>{menu_state.notification_time}min</b>")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row(*((f"+{step}", f"time_+{step}") for step in self.TIME_STEPS))
            keyboard.add_row(*((f"-{step}", f"time_-{step}") for step in self.TIME_STEPS))
            keyboard.add_row(("{emo:save} Save", "time_save"), (BACK_LABEL, ""))

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _settings_menu(self, command_context: CommandContext) -> None:
        """Show the notification settings currently stored in the plugin settings."""
        notification_height = self.plugin_context.settings.notification_height
        notification_time = self.plugin_context.settings.notification_time

        menu_state = SettingsMenuState(notification_height, notification_time)

        msg = render_emojis(
            "{emo:settings} <b>Current notification settings are:</b>\n\n"
            f"{{emo:height}} Height: {notification_height:.2f}mm\n\n"
            f"{{emo:alarmclock}} Time: {notification_time:d}min\n\n"
        )

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(("{emo:height} Set height", "height"), ("{emo:alarmclock} Set time", "time"))
        keyboard.add_row(CLOSE_BUTTON)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
