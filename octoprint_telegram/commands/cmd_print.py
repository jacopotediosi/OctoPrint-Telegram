import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdPrint(BaseCommand):
    def execute(self, context: CommandContext):
        if not self.main._printer.is_ready():
            msg = f"{get_emoji('warning')} Can't start a new print, printer is not ready. Printer status: {self.main._printer.get_state_string()}."
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        current_data = self.main._printer.get_current_data()
        job_file_name = current_data.get("job", {}).get("file", {}).get("name", "")

        if context.parameter == "y":  # Print the loaded file
            if current_data.get("job", {}).get("file", {}).get("name") is None:
                self.main.send_msg(
                    f"{get_emoji('attention')} No file is selected for printing. Did you select one using /files?",
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
                return

            self.main._printer.start_print(user=context.user)

            self.main.send_msg(
                f"{get_emoji('rocket')} Started printing <code>{html.escape(job_file_name)}</code>.",
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )
        else:  # Propose to print the loaded file or to open /files
            if job_file_name:
                msg = (
                    f"{get_emoji('info')} The file <code>{html.escape(job_file_name)}</code> is loaded.\n\n"
                    f"{get_emoji('question')} What do you want to do?"
                )

                command_buttons = [
                    [
                        [
                            f"{get_emoji('play')} Print it",
                            f"{context.cmd}_y",
                        ],
                        [
                            f"{get_emoji('folder')} Select another one",
                            "/files",
                        ],
                    ],
                    [
                        [
                            f"{get_emoji('cancel')} Close",
                            "close",
                        ],
                    ],
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
            else:
                self.main.send_msg(
                    f"{get_emoji('warning')} No file is loaded. Please select one using /files.",
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
