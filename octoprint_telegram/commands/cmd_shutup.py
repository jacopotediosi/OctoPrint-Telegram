from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdShutup(BaseCommand):
    def execute(self, context: CommandContext):
        self.main.shut_up.add(context.chat_id)

        msg = render_emojis(
            "{emo:nonotify} Okay, shutting up until the next print is finished.\n"
            "Use /dontshutup to let me talk again before that."
        )

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
