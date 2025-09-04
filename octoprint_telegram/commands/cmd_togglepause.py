from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdTogglePause(BaseCommand):
    def execute(self, context: CommandContext):
        if self.main._printer.is_printing():
            msg = f"{get_emoji('pause')} Pausing the print."
            self.main._printer.pause_print(user=context.user)
        elif self.main._printer.is_paused():
            msg = f"{get_emoji('resume')} Resuming the print."
            self.main._printer.resume_print(user=context.user)
        else:
            msg = f"{get_emoji('warning')} Currently I'm not printing, so there is nothing to pause/resume."

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
