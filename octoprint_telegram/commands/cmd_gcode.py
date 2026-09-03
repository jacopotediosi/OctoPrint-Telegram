import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup
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
            self.send_answer(
                command_context,
                render_emojis("{emo:attention} Printer not connected. You can't send any G-code."),
                None,
            )
            return

        if not command_context.parameter:
            msg = "{emo:info} Reply to this message with the G-code you want to execute"
            if self.plugin_context.printer.is_printing():
                msg += "\n\n{emo:warning} A print is in progress. Sending G-code may interfere with it."

            self.send_answer(
                command_context,
                render_emojis(msg),
                None,
                markup=Markup.HTML,
                force_reply=True,
            )
            return

        command = command_context.parameter

        self.plugin_context.printer.commands(command)

        self.send_answer(
            command_context,
            render_emojis(f"{{emo:check}} G-code <code>{html.escape(command)}</code> sent!"),
            None,
            markup=Markup.HTML,
        )
