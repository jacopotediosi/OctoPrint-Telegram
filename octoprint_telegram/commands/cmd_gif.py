from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdGif(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        if self.plugin_context.settings.send_gif:
            msg = render_emojis("{emo:video} Here are your GIF(s)")
            with_gif = True
        else:
            msg = render_emojis("{emo:notallowed} Sending GIFs is disabled in plugin settings")
            with_gif = False

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            with_gif=with_gif,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
