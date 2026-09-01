import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup, ReplyPrompt
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdGcode(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Send a G-code command to the printer.

        Possible callback queries:

        - /gcode -> ask for the G-code command to send

        Replying to that request runs the command again, with the reply as its parameter.
        """
        if not self.plugin_context.printer.is_operational():
            self.plugin_context.sender.send_message(
                render_emojis("{emo:attention} Printer not connected. You can't send any G-code."),
                chat_id=command_context.chat_id,
                message_id=command_context.msg_id_to_update,
                reply_to_message_id=command_context.msg_id_to_reply_to,
            )
            return

        if not command_context.parameter:
            self.update_menu(
                command_context,
                render_emojis("{emo:info} Reply to this message with the G-code you want to execute"),
                ReplyPrompt(command_context.cmd),
                markup=Markup.HTML,
                force_reply=True,
            )
            return

        command = command_context.parameter

        self.plugin_context.printer.commands(command)

        self.plugin_context.sender.send_message(
            render_emojis(f"{{emo:check}} G-code <code>{html.escape(command)}</code> sent!"),
            chat_id=command_context.chat_id,
            markup=Markup.HTML,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
