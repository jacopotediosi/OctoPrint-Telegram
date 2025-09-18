from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdSuperGif(BaseCommand):
    SUPERGIF_DURATION = 10

    def execute(self, context: CommandContext):
        if self.main._settings.get(["send_gif"]):
            msg = render_emojis("{emo:video} Here are your GIF(s)")
            with_gif = True
        else:
            msg = render_emojis("{emo:notallowed} Sending GIFs is disabled in plugin settings")
            with_gif = False

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            with_gif=with_gif,
            gif_duration=self.SUPERGIF_DURATION,
            msg_id=context.msg_id_to_update,
        )
