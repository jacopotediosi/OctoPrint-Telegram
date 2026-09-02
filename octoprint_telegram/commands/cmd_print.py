import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdPrint(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Print the file selected for printing.

        Possible callback queries:

        - /print -> ask whether to print the file selected for printing, or report that none is selected
        - /print_yes -> start printing the file selected for printing
        """
        if not self.plugin_context.printer.is_ready():
            msg = render_emojis(
                f"{{emo:warning}} Can't start a new print, printer is not ready. Printer status: {self.plugin_context.printer.get_state_string()}."
            )
            self.send_answer(command_context, msg, None)
            return

        current_data = self.plugin_context.printer.get_current_data()
        job_file_name = current_data.get("job", {}).get("file", {}).get("name", "")

        if command_context.parameter == "yes":  # Print the file selected for printing
            if current_data.get("job", {}).get("file", {}).get("name") is None:
                self.send_answer(
                    command_context,
                    render_emojis("{emo:attention} No file is selected for printing. Did you select one using /files?"),
                    None,
                )
                return

            self.plugin_context.printer.start_print(user=command_context.user)

            self.send_answer(
                command_context,
                render_emojis(f"{{emo:rocket}} Started printing <code>{html.escape(job_file_name)}</code>."),
                None,
                markup=Markup.HTML,
            )
        else:  # Propose to print the file selected for printing or to open /files
            if job_file_name:
                msg = render_emojis(
                    f"{{emo:info}} The file <code>{html.escape(job_file_name)}</code> is selected for printing.\n\n"
                    "{emo:question} What do you want to do?"
                )

                command_buttons = [
                    [
                        (
                            render_emojis("{emo:play} Print it"),
                            f"{command_context.cmd}_yes",
                        ),
                        (
                            render_emojis("{emo:folder} Select another one"),
                            "/files",
                        ),
                    ],
                    [
                        (
                            render_emojis("{emo:cancel} Close"),
                            "close",
                        ),
                    ],
                ]

                self.send_answer(command_context, msg, None, markup=Markup.HTML, buttons=command_buttons)
            else:
                self.send_answer(
                    command_context,
                    render_emojis("{emo:warning} No file is selected for printing. Please select one using /files."),
                    None,
                )
