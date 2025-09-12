import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdGcode(BaseCommand):
    def execute(self, context: CommandContext):
        if not self.main._printer.is_operational():
            self.main.send_msg(
                render_emojis("{emo:attention} Printer not connected. You can't send any G-code."),
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        if context.parameter:
            command = context.parameter

            self.main._printer.commands(command)

            msg = render_emojis(f"{{emo:check}} G-code <code>{html.escape(command)}</code> sent!")
        else:
            msg = render_emojis(
                f"{{emo:info}} Use <code>{context.cmd}_XXX</code> to call the command, where <code>XXX</code> is the G-code you want to execute"
            )

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            msg_id=context.msg_id_to_update,
        )
