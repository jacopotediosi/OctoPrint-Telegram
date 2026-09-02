import html

import octoprint.filemanager
from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdUpload(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        supported_extensions = ", ".join(
            [f"<code>{html.escape(f'.{ext}')}</code>" for ext in octoprint.filemanager.get_all_extensions()]
        )

        msg = render_emojis(
            "{emo:info} To upload a file, attach it in reply to this message.\n\n"
            "The file will be stored in the <code>TelegramPlugin</code> folder.\n\n"
            f"Allowed file extensions are: {supported_extensions}, or a ZIP file containing them."
        )

        self.send_answer(command_context, msg, None, markup=Markup.HTML)
