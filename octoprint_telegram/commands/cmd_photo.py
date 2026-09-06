from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdPhoto(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        msg = render_emojis("{emo:photo} Here are your photo(s)")
        self.send_answer(command_context, msg, None, with_image=True)
