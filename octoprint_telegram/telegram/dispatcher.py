from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from ..commands import registry
from ..domain import permissions
from ..domain.chats import get_chat_title
from ..domain.uploads import Uploads
from ..emoji import Emoji
from .enums import ChatMemberStatus, HttpMethod

if TYPE_CHECKING:
    from ..commands.commands import Commands
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis


class Dispatcher:
    """Routes each update Telegram sends to whatever handles it."""

    def __init__(self, plugin_context: PluginContext, commands: Commands):
        self.plugin_context = plugin_context
        self._commands = commands
        self._uploads = Uploads(plugin_context)
        self._logger = plugin_context.logger.getChild("Dispatcher")

    def process_update(self, update):
        self._logger.debug("Processing update: %s", update)

        chat_id = self._get_chat_id(update)
        from_id = self._get_from_id(update)

        is_chat_unknown = self.plugin_context.chats.get_chat(chat_id) is None
        if is_chat_unknown and not self.plugin_context.enrollment.is_open:
            self._logger.warning("Received an update from unknown chat %s while enrollment is disabled", chat_id)
            return

        if "message" in update or "channel_post" in update:
            message = update.get("message", update.get("channel_post"))

            # We got a text message, likely a command
            if "text" in message:
                if is_chat_unknown:
                    self._logger.info("Received a text message from unknown chat %s, enrolling it...", chat_id)
                    chat = message["chat"]
                    chat_title = get_chat_title(chat)
                    chat_type = chat["type"]
                    self._enroll_chat(chat_id, chat_title, chat_type)
                else:
                    self._handle_text_message(message, chat_id, from_id)
            # We got a document (file)
            elif "document" in message:
                self._uploads.store_document(message, chat_id, from_id)
            # We got message with notification for a new chat title so lets update it
            elif "new_chat_title" in message:
                self._handle_new_chat_title_message(message, chat_id, from_id)
            # We got message with notification for a new chat title photo so lets download it
            elif "new_chat_photo" in message or "delete_chat_photo" in message:
                self._handle_new_chat_photo_message(update, chat_id, from_id)
            # At this point we don't know what message type it is, so we do nothing
            else:
                self._logger.debug("Got an unknown message. Doing nothing. Update was: %s", update)
        # Triggered when the user clicks on inline buttons
        elif "callback_query" in update:
            self._handle_callback_query(update["callback_query"], chat_id, from_id)
        # Triggered when the bot's role in a chat changes (e.g., added, removed, promoted to admin, blocked in private chat, etc.)
        elif "my_chat_member" in update:
            self._handle_my_chat_member(update["my_chat_member"], chat_id, from_id)
        else:
            self._logger.debug("Got an unknown update. Doing nothing. Update was: %s", update)

    def _handle_my_chat_member(self, my_chat_member, chat_id, from_id):
        status = my_chat_member.get("new_chat_member", {}).get("status", "")

        try:
            new_status = ChatMemberStatus(status)
        except ValueError:
            self._logger.warning("Ignoring an unknown chat member status: %s", status)
            return

        if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
            # If it is a new chat, add it to the known chats
            if self.plugin_context.chats.get_chat(chat_id) is None:
                self._logger.info("The bot has been added to the new chat %s, enrolling it...", chat_id)
                chat = my_chat_member["chat"]
                chat_title = get_chat_title(chat)
                chat_type = chat["type"]
                self._enroll_chat(chat_id, chat_title, chat_type)

        elif (
            new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
            and self.plugin_context.chats.get_chat(chat_id) is not None
        ):
            # The bot left the chat, delete it from known chats
            self._logger.info("The bot left chat %s, removing it from settings...", chat_id)
            self.plugin_context.chats.remove_chat(chat_id)

    def _enroll_chat(self, chat_id, chat_title, chat_type):
        """Add a chat to the known chats and tell it that its permissions still have to be configured."""
        self.plugin_context.chats.add_chat(chat_id, chat_title, chat_type)
        self.plugin_context.sender.send_message(
            render_emojis(
                "{emo:info} Chat added to known chats. "
                "Before you can do anything, please go to plugin settings and edit your permissions."
            ),
            chat_id,
        )

    def _handle_new_chat_title_message(self, message, chat_id, from_id):
        self._logger.info("Chat %s changed title, updating it...", chat_id)

        chat = message["chat"]

        self.plugin_context.settings.set_chat_field(chat_id, "title", get_chat_title(chat))
        self.plugin_context.settings.save()
        self.plugin_context.frontend.update_known_chats(self.plugin_context.settings.chats)

    def _handle_new_chat_photo_message(self, message, chat_id, from_id):
        self._logger.info("Chat %s changed picture, updating it...", chat_id)

        try:

            def update_chat_picture():
                public_path = self.plugin_context.chats.save_chat_picture(chat_id)
                self.plugin_context.settings.set_chat_field(chat_id, "image", public_path)
                self.plugin_context.settings.save()
                self.plugin_context.frontend.update_known_chats(self.plugin_context.settings.chats)

            threading.Thread(target=update_chat_picture, daemon=True).start()
        except Exception:
            self._logger.exception("Caught an exception updating chat picture for chat_id %s", chat_id)

    def _handle_text_message(self, message, chat_id, from_id):
        message_text = message["text"]

        if not message_text.startswith("/"):
            self._logger.debug("Ignoring text message '%s' because it doesn't start with a slash", message_text)
            return

        # Remove bot username from commands like /command@botusername
        command = message_text.split("@")[0]

        self._handle_command(command, chat_id, from_id, message.get("from"))

    def _handle_callback_query(self, callback_query, chat_id, from_id):
        command = callback_query["data"]
        from_obj = callback_query["from"]
        msg_id_to_update = callback_query.get("message", {}).get("message_id", "")

        # Handle callback query data as if it was a text command
        try:
            self._handle_command(command, chat_id, from_id, from_obj, msg_id_to_update)
        except Exception:
            self._logger.exception("Caught an exception calling _handle_command()")

        # Answer callback query (to prevent inline buttons from continuing to blink)
        try:
            self.plugin_context.telegram_client.send_request(
                "answerCallbackQuery",
                HttpMethod.POST,
                data={"callback_query_id": callback_query["id"]},
            )
        except Exception:
            self._logger.exception("Caught an exception sending answerCallbackQuery")

    def _handle_command(self, command, chat_id, from_id, from_obj, msg_id_to_update=""):
        # Separate command and parameter
        parts = command.split("_")
        command = parts[0].lower()
        command_definition = registry.get(command)
        parameter = "_".join(parts[1:]) if command_definition is not None and command_definition.takes_parameter else ""

        # Log received command
        self._logger.info(
            "Received command '%s' with parameter '%s' in chat '%s' from '%s'", command, parameter, chat_id, from_id
        )

        # Is command  known?
        if command_definition is None:
            # we dont know the command so skip the message
            self._logger.warning("Previous command was an unknown command.")
            if not self.plugin_context.settings.no_mistake:
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:notallowed} I do not understand you!"),
                    chat_id,
                )
            return

        # Check if user is allowed to execute the command
        if permissions.is_command_allowed(self.plugin_context.settings, chat_id, from_id, command):
            # Identify user
            user = "Telegram - "
            try:
                username = from_obj.get("username")

                first_name = from_obj.get("first_name")
                last_name = from_obj.get("last_name")
                fullname = " ".join(part for part in (first_name, last_name) if part).strip()

                parts = []

                if username:
                    parts.append(f"@{username}")
                if fullname:
                    parts.append(fullname)

                user += " - ".join(parts) if parts else "UNKNOWN"
            except Exception:
                user += "UNKNOWN"

            # Execute command
            try:
                self._commands.run_command(command, chat_id, from_id, parameter, msg_id_to_update, user)
            except Exception:
                self._logger.exception("Caught an exception executing command %s", command)
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:attention} Error executing your command! Please check logs."),
                    chat_id,
                    message_id=msg_id_to_update,
                )
        else:
            # User was not allowed to execute this command
            self._logger.warning("Previous command was from an unauthorized user.")
            self.plugin_context.sender.send_message(
                render_emojis("{emo:notallowed} You are not allowed to do this!"),
                chat_id,
            )

    def _get_chat_id(self, update):
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
        elif "callback_query" in update:
            chat_id = update["callback_query"]["message"]["chat"]["id"]
        elif "my_chat_member" in update:
            chat_id = update["my_chat_member"]["chat"]["id"]
        elif "channel_post" in update:
            chat_id = update["channel_post"]["chat"]["id"]
        else:
            raise ValueError(
                "Unsupported update type: no 'message' or 'callback_query' or 'my_chat_member' or 'channel_post' found"
            )

        return str(chat_id)

    def _get_from_id(self, update):
        if "message" in update:
            from_id = update.get("message", {}).get("from", {}).get("id", "")
        elif "callback_query" in update:
            from_id = update.get("callback_query", {}).get("from", {}).get("id", "")
        elif "my_chat_member" in update:
            from_id = update.get("my_chat_member", {}).get("from", {}).get("id", "")
        elif "channel_post" in update:
            from_id = update.get("channel_post", {}).get("from", {}).get("id", "")
        else:
            raise ValueError("Unsupported update type: no 'message' or 'callback_query' or 'my_chat_member' found")

        return str(from_id)
