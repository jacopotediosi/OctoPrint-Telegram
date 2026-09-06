from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdSuperGif(BaseCommand):
    SUPERGIF_DURATION = 10

    @override
    def execute(self, command_context: CommandContext) -> None:
        if self.plugin_context.settings.send_gif:
            msg = render_emojis("{emo:video} Here are your GIF(s)")
            with_gif = True
        else:
            msg = render_emojis("{emo:notallowed} Sending GIFs is disabled in plugin settings")
            with_gif = False

        self.send_answer(command_context, msg, None, with_gif=with_gif, gif_duration=self.SUPERGIF_DURATION)
