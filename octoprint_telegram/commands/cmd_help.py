import html

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdHelp(BaseCommand):
    def execute(self, command_context: CommandContext) -> None:
        commands = sorted(
            (command.name, command.description)
            for command in self.plugin_context.command_definitions
            if command.shown_to_users
        )

        msg = render_emojis("{emo:info} <b>The following commands are available:</b>\n\n")
        msg += "\n".join(f"{html.escape(name)} - {html.escape(description)}" for name, description in commands)

        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            markup=Markup.HTML,
            message_id=command_context.msg_id_to_update,
        )
