import html

import octoprint.filemanager

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdUpload(BaseCommand):
    def execute(self, context: CommandContext):
        supported_extensions = ", ".join(
            [f"<code>{html.escape(f'.{ext}')}</code>" for ext in octoprint.filemanager.get_all_extensions()]
        )

        msg = render_emojis(
            "{emo:info} To upload a file, attach it in reply to this message.\n\n"
            "The file will be stored in the <code>TelegramPlugin</code> folder.\n\n"
            f"Allowed file extensions are: {supported_extensions}, or a ZIP file containing them."
        )

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            msg_id=context.msg_id_to_update,
        )
