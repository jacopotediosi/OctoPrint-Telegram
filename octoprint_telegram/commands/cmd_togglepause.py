from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdTogglePause(BaseCommand):
    def execute(self, command_context: CommandContext) -> None:
        if self.plugin_context.printer.is_printing():
            msg = render_emojis("{emo:pause} Pausing the print.")
            self.plugin_context.printer.pause_print(user=command_context.user)
        elif self.plugin_context.printer.is_paused():
            msg = render_emojis("{emo:resume} Resuming the print.")
            self.plugin_context.printer.resume_print(user=command_context.user)
        else:
            msg = render_emojis("{emo:warning} Currently I'm not printing, so there is nothing to pause/resume.")

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
        )
