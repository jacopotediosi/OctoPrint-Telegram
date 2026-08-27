import html

import octoprint.filemanager

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdUpload(BaseCommand):
    def execute(self, command_context: CommandContext):
        supported_extensions = ", ".join(
            [f"<code>{html.escape(f'.{ext}')}</code>" for ext in octoprint.filemanager.get_all_extensions()]
        )

        msg = render_emojis(
            "{emo:info} To upload a file, attach it in reply to this message.\n\n"
            "The file will be stored in the <code>TelegramPlugin</code> folder.\n\n"
            f"Allowed file extensions are: {supported_extensions}, or a ZIP file containing them."
        )

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            markup=Markup.HTML,
            message_id=command_context.msg_id_to_update,
        )
