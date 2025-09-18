from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdHome(BaseCommand):
    def execute(self, context: CommandContext):
        if self.main._printer.is_ready():
            msg = render_emojis("{emo:home} Homing.")
            self.main._printer.home(["x", "y", "z"])
        else:
            msg = render_emojis("{emo:attention} I can't go home now.")

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
