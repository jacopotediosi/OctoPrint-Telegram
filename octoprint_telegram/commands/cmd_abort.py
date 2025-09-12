from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdAbort(BaseCommand):
    def execute(self, context: CommandContext):
        if context.parameter == "stop":
            self.main._printer.cancel_print(user=context.user)

            msg = render_emojis("{emo:check} Aborting the print.")

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
        else:
            if self.main._printer.is_printing() or self.main._printer.is_pausing() or self.main._printer.is_paused():
                msg = render_emojis("{emo:question} Really abort the currently running print?")

                command_buttons = [
                    [
                        [
                            render_emojis("{emo:check} Stop print"),
                            f"{context.cmd}_stop",
                        ],
                        [render_emojis("{emo:cancel} Close"), "close"],
                    ]
                ]

                self.main.send_msg(
                    msg,
                    responses=command_buttons,
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
            else:
                msg = render_emojis("{emo:warning} Currently I'm not printing, so there is nothing to stop.")

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
