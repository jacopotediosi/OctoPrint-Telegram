import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdHelp(BaseCommand):
    def execute(self, context: CommandContext):
        commands = [
            (cmd, info.get("desc", "No description provided"))
            for cmd, info in self.main.commands.commands_dict.items()
            if cmd.startswith("/")
        ]
        commands.sort()

        msg = render_emojis("{emo:info} <b>The following commands are available:</b>\n\n")
        msg += "\n".join(f"{html.escape(cmd)} - {html.escape(desc)}" for cmd, desc in commands)

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            msg_id=context.msg_id_to_update,
        )
