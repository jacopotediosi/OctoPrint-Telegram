from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdDontShutup(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        self.plugin_context.muted_chats.unmute_chat(command_context.chat_id)

        msg = render_emojis("{emo:notify} Yay, I can talk again.")

        self.send_answer(command_context, msg, None)
