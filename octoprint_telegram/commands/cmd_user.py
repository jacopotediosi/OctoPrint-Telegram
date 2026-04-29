import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdUser(BaseCommand):
    def execute(self, context: CommandContext):
        # Gather data
        chat_settings = self.main._settings.get(["chats", context.chat_id])
        from_settings = self.main._settings.get(["chats", context.from_id])

        # -- Chat and user information section --

        msg = render_emojis(
            "{emo:info} <b>Chat and user information:</b>\n\n"
            f"<b>Chat title:</b> {html.escape(chat_settings['title'])}\n"
            f"<b>Chat type:</b> {html.escape(chat_settings['type'])}\n"
            f"<b>Chat id:</b> {html.escape(context.chat_id)}\n"
            f"<b>User id:</b> {html.escape(context.from_id)}\n\n"
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
        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            msg_id=context.msg_id_to_update,
        )
