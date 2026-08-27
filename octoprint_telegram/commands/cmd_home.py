from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdHome(BaseCommand):
    def execute(self, command_context: CommandContext):
        if self.plugin_context.printer.is_ready():
            msg = render_emojis("{emo:home} Homing.")
            self.plugin_context.printer.home(["x", "y", "z"])
        else:
            msg = render_emojis("{emo:attention} I can't go home now.")

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
        )
