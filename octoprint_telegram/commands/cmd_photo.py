from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdPhoto(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        msg = render_emojis("{emo:photo} Here are your photo(s)")
        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            with_image=True,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
