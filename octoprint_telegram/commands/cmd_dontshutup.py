from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdDontShutup(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        self.plugin_context.muted_chats.unmute_chat(command_context.chat_id)

        msg = render_emojis("{emo:notify} Yay, I can talk again.")

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
