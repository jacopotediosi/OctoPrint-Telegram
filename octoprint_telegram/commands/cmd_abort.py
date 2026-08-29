from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdAbort(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        if command_context.parameter == "stop":
            self.plugin_context.printer.cancel_print(user=command_context.user)

            msg = render_emojis("{emo:check} Aborting the print.")

            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                message_id=command_context.msg_id_to_update,
            )
        else:
            if (
                self.plugin_context.printer.is_printing()
                or self.plugin_context.printer.is_pausing()
                or self.plugin_context.printer.is_paused()
            ):
                msg = render_emojis("{emo:question} Really abort the currently running print?")

                command_buttons = [
                    [
                        (
                            render_emojis("{emo:check} Stop print"),
                            f"{command_context.cmd}_stop",
                        ),
                        (render_emojis("{emo:cancel} Close"), "close"),
                    ]
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    buttons=command_buttons,
                    chat_id=command_context.chat_id,
                    message_id=command_context.msg_id_to_update,
                )
            else:
                msg = render_emojis("{emo:warning} Currently I'm not printing, so there is nothing to stop.")

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    message_id=command_context.msg_id_to_update,
                )
