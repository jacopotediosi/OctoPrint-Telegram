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
        else:
            msg = render_emojis("{emo:attention} I can't go home now.")

        self.send_answer(command_context, msg, None)
