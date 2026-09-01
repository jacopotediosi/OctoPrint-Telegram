import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdUser(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        # Gather data
        chat_settings = self.plugin_context.chats.get_chat(command_context.chat_id) or {}
        from_settings = self.plugin_context.chats.get_chat(command_context.from_id)

        # -- Chat and user information section --

        msg = render_emojis(
            "{emo:info} <b>Chat and user information:</b>\n\n"
            f"<b>Chat title:</b> {html.escape(chat_settings['title'])}\n"
            f"<b>Chat type:</b> {html.escape(chat_settings['type'])}\n"
            f"<b>Chat id:</b> {html.escape(command_context.chat_id)}\n"
            f"<b>User id:</b> {html.escape(command_context.from_id)}\n\n"
        )

        # -- Commands allowed section --

        enabled_group_commands = []
        if chat_settings["accept_commands"]:
            enabled_group_commands = [command for command, enabled in chat_settings["commands"].items() if enabled]

        enabled_individual_commands = []
        if chat_settings["allow_users"] and from_settings:
            enabled_individual_commands = [command for command, enabled in from_settings["commands"].items() if enabled]

        if enabled_group_commands:
            msg += "<b>All chat members can use the following commands:</b>\n"
            escaped_commands = [html.escape(command) for command in enabled_group_commands]
            msg += ", ".join(escaped_commands) + "\n\n"

        if enabled_individual_commands:
            also_text = "also " if enabled_group_commands else ""
            msg += f"<b>You can {also_text}use the following commands (individually enabled):</b>\n"
            escaped_commands = [html.escape(command) for command in enabled_individual_commands]
            msg += ", ".join(escaped_commands) + "\n\n"

        if not enabled_group_commands and not enabled_individual_commands:
            msg += "No commands allowed\n\n"

        # -- Notifications enabled section --

        msg += "<b>Notifications enabled for this chat:</b>\n"

        enabled_notifications = []
        if chat_settings["send_notifications"]:
            enabled_notifications = [
                notification for notification, enabled in chat_settings["notifications"].items() if enabled
            ]
        if enabled_notifications:
            escaped_notifications = [html.escape(notification) for notification in enabled_notifications]
            msg += ", ".join(escaped_notifications) + "\n\n"
        else:
            msg += "No notifications enabled"

        # Send the message
        self.plugin_context.sender.send_message(
            msg,
            chat_id=command_context.chat_id,
            markup=Markup.HTML,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
