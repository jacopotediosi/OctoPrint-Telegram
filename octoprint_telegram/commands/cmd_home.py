from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdHome(BaseCommand):
    def execute(self, context: CommandContext):
        if self.main._printer.is_ready():
            msg = f"{get_emoji('home')} Homing."
            self.main._printer.home(["x", "y", "z"])
        else:
            msg = f"{get_emoji('attention')} I can't go home now."

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
