from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdDontShutup(BaseCommand):
    def execute(self, context: CommandContext):
        self.main.shut_up.discard(context.chat_id)

        msg = render_emojis("{emo:notify} Yay, I can talk again.")

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
