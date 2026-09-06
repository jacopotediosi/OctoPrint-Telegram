from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdHome(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        if self.plugin_context.printer.is_ready():
            msg = render_emojis("{emo:home} Homing.")
            self.plugin_context.printer.home(["x", "y", "z"])
        elif self.plugin_context.printer.is_closed_or_error():
            msg = render_emojis("{emo:attention} I can't go home now, not connected to a printer. Use /con to connect.")
        else:
            msg = render_emojis(
                f"{{emo:attention}} I can't go home now, printer is busy. Printer status: {self.plugin_context.printer.get_state_string()}."
            )

        self.send_answer(command_context, msg, None)
