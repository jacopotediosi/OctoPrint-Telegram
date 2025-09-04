from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdShutup(BaseCommand):
    def execute(self, context: CommandContext):
        self.main.shut_up.add(context.chat_id)

        msg = (
            f"{get_emoji('nonotify')} Okay, shutting up until the next print is finished.\n"
            f"Use /dontshutup to let me talk again before that."
        )

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
