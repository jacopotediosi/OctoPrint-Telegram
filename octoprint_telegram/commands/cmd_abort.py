from typing_extensions import override

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdAbort(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Abort the running print.

        Possible callback queries:

        - /abort -> ask whether to abort the running print, or report that no print is running
        - /abort_stop -> cancel the running print
        """
        if command_context.parameter == "stop":
            self.plugin_context.printer.cancel_print(user=command_context.user)

            msg = render_emojis("{emo:check} Aborting the print.")

            self.send_answer(command_context, msg, None)
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

                self.send_answer(command_context, msg, None, buttons=command_buttons)
            else:
                msg = render_emojis("{emo:warning} Currently I'm not printing, so there is nothing to stop.")

                self.send_answer(command_context, msg, None)
