from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdShutup(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        self.plugin_context.muted_chats.mute_chat(command_context.chat_id)

        msg = render_emojis(
            "{emo:nonotify} Okay, shutting up until the next print is finished.\n"
            "Use /dontshutup to let me talk again before that."
        )

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
        )
