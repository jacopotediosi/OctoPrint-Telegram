from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdPhoto(BaseCommand):
    def execute(self, context: CommandContext):
        msg = render_emojis("{emo:photo} Here are your photo(s)")
        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            with_image=True,
            msg_id=context.msg_id_to_update,
        )
