import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import CLOSE_BUTTON, Keyboard, Markup, MenuState, StaleMenuError
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class AbortMenuState(MenuState):
    """The print the menu offers to abort."""

    def __init__(self, file_path: str) -> None:
        """Set up the print the menu offers to abort.

        Args:
            file_path (str): The path of the file being printed, its storage included.
        """
        self.file_path = file_path


class CmdAbort(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Abort the running print.

        Possible callback queries:

        - /abort -> ask whether to abort the running print, or report that no print is running
        - /abort_stop -> cancel the print the confirmation was asked for

        Raises:
            StaleMenuError: If the print the menu offers to abort is no longer the running one.
        """
        if command_context.parameter == "stop":
            menu_state = self.require_menu_state(command_context, AbortMenuState)

            job_file = self.plugin_context.printer.get_current_data().get("job", {}).get("file", {})
            if f"{job_file.get('origin')}/{job_file.get('path')}" != menu_state.file_path:
                raise StaleMenuError

            self.plugin_context.printer.cancel_print(user=command_context.user)

            msg = render_emojis("{emo:check} Aborting the print.")

            self.send_answer(command_context, msg, None)
        else:
            if (
                self.plugin_context.printer.is_printing()
                or self.plugin_context.printer.is_pausing()
                or self.plugin_context.printer.is_paused()
            ):
                job_file = self.plugin_context.printer.get_current_data().get("job", {}).get("file", {})
                file_path = f"{job_file.get('origin')}/{job_file.get('path')}"

                msg = render_emojis(f"{{emo:question}} Really abort printing <code>/{html.escape(file_path)}</code>?")

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row(("{emo:check} Stop print", "stop"), CLOSE_BUTTON)

                self.send_answer(command_context, msg, AbortMenuState(file_path), markup=Markup.HTML, keyboard=keyboard)
            else:
                msg = render_emojis("{emo:warning} Currently I'm not printing, so there is nothing to stop.")

                self.send_answer(command_context, msg, None)
