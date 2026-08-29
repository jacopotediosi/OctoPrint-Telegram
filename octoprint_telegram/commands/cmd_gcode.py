import html

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdGcode(BaseCommand):
    def execute(self, command_context: CommandContext) -> None:
        if not self.plugin_context.printer.is_operational():
            self.plugin_context.sender.send_message(
                render_emojis("{emo:attention} Printer not connected. You can't send any G-code."),
                chat_id=command_context.chat_id,
                message_id=command_context.msg_id_to_update,
            )
            return

        if command_context.parameter:
            command = command_context.parameter

            self.plugin_context.printer.commands(command)

            msg = render_emojis(f"{{emo:check}} G-code <code>{html.escape(command)}</code> sent!")
        else:
            msg = render_emojis(
                f"{{emo:info}} Use <code>{command_context.cmd}_XXX</code> to call the command, where <code>XXX</code> is the G-code you want to execute"
            )

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            markup=Markup.HTML,
            message_id=command_context.msg_id_to_update,
        )
