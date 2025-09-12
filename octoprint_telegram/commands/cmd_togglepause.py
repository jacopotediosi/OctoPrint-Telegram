from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdTogglePause(BaseCommand):
    def execute(self, context: CommandContext):
        if self.main._printer.is_printing():
            msg = render_emojis("{emo:pause} Pausing the print.")
            self.main._printer.pause_print(user=context.user)
        elif self.main._printer.is_paused():
            msg = render_emojis("{emo:resume} Resuming the print.")
            self.main._printer.resume_print(user=context.user)
        else:
            msg = render_emojis("{emo:warning} Currently I'm not printing, so there is nothing to pause/resume.")

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
