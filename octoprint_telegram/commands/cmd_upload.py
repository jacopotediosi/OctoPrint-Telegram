from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdUpload(BaseCommand):
    def execute(self, context: CommandContext):
        msg = render_emojis(
            "{emo:info} To upload a G-code file (a ZIP file is also accepted), reply to this message with your file.\n"
            "The file will be stored in the 'TelegramPlugin' folder."
        )

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            msg_id=context.msg_id_to_update,
        )
