from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdPhoto(BaseCommand):
    def execute(self, context: CommandContext):
        msg = f"{get_emoji('photo')} Here are your photo(s)"
        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            with_image=True,
            msg_id=context.msg_id_to_update,
        )
