from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdGif(BaseCommand):
    def execute(self, context: CommandContext):
        if self.main._settings.get(["send_gif"]):
            msg = f"{get_emoji('video')} Here are your GIF(s)"
            with_gif = True
        else:
            msg = f"{get_emoji('notallowed')} Sending GIFs is disabled in plugin settings"
            with_gif = False

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            with_gif=with_gif,
            msg_id=context.msg_id_to_update,
        )
