from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

from ..commands import registry
from ..commands.base import CommandContext
from ..domain import permissions
from ..domain.chats import get_chat_title, is_group_or_channel
from ..domain.uploads import Uploads
from ..emoji import Emoji
from .enums import ChatMemberStatus, HttpMethod
from .menu_states import StaleMenuError

if TYPE_CHECKING:
    from ..commands.commands import Commands
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis

SUPPORTED_UPDATE_TYPES = ("message", "callback_query", "my_chat_member", "channel_post")

WORKER_IDLE_TIMEOUT_SECONDS = 10


class Dispatcher:
    """Routes each update Telegram sends to whatever handles it."""

    def __init__(self, plugin_context: PluginContext, commands: Commands) -> None:
        """Set up the routing of the updates Telegram sends.

        Args:
            plugin_context (PluginContext): The plugin context.
            commands (Commands): The bot commands, ready to run.
        """
        self.plugin_context = plugin_context
        self._commands = commands
        self._uploads = Uploads(plugin_context)
        self._logger = plugin_context.logger.getChild("Dispatcher")
        self._queues: dict[str, queue.Queue[dict]] = {}
        self._queues_lock = threading.Lock()

    def process_update(self, update: dict) -> None:
        """Hand one update to the worker serving its chat.

        Updates from the same chat are processed in arrival order. Each known chat is served by its own worker;
        the chats the bot does not know all share one.

        Args:
            update (dict): The update as Telegram sent it.

        Raises:
            ValueError: If the update is of a type the bot does not handle.
        """
        chat_id, _ = self._get_chat_and_from_ids(update)

        key = chat_id if self.plugin_context.chats.get_chat(chat_id) is not None else "unknown"

        with self._queues_lock:
            updates_queue = self._queues.get(key)
            if updates_queue is None:
                updates_queue = queue.Queue()
                threading.Thread(target=self._work, args=(key, updates_queue), daemon=True).start()
                self._queues[key] = updates_queue

            updates_queue.put(update)

    def _work(self, key: str, updates_queue: queue.Queue[dict]) -> None:
        while True:
            try:
                update = updates_queue.get(timeout=WORKER_IDLE_TIMEOUT_SECONDS)
            except queue.Empty:
                with self._queues_lock:
                    if updates_queue.empty():
                        del self._queues[key]
                        return
                continue

            try:
                self._process_update(update)
            except Exception:
                self._logger.exception("Caught an exception processing an update")

    def _process_update(self, update: dict) -> None:
        """Route one update to whatever handles it.

        Args:
            update (dict): The update as Telegram sent it.
        """
        self._logger.debug("Processing update: %s", update)

        chat_id, from_id = self._get_chat_and_from_ids(update)

        is_chat_unknown = self.plugin_context.chats.get_chat(chat_id) is None
        if is_chat_unknown and not self.plugin_context.enrollment.is_open:
            self._logger.warning("Received an update from unknown chat %s while enrollment is disabled", chat_id)
            return

        if "message" in update or "channel_post" in update:
            message = update.get("message", update.get("channel_post"))
            msg_id_to_reply_to = str(message["message_id"]) if is_group_or_channel(chat_id) else ""

            # We got a text message, likely a command
            if "text" in message:
                if is_chat_unknown:
                    self._logger.info("Received a text message from unknown chat %s, enrolling it...", chat_id)
                    chat = message["chat"]
                    chat_title = get_chat_title(chat)
                    chat_type = chat["type"]
                    self._enroll_chat(chat_id, chat_title, chat_type, msg_id_to_reply_to)
                else:
                    self._handle_text_message(message, chat_id, from_id, msg_id_to_reply_to)
            # We got a document (file)
            elif "document" in message:
                self._uploads.store_document(message, chat_id, from_id, msg_id_to_reply_to)
            # We got message with notification for a new chat title so lets update it
            elif "new_chat_title" in message:
                self._handle_new_chat_title_message(message, chat_id)
            # We got message with notification for a new chat title photo so lets download it
            elif "new_chat_photo" in message or "delete_chat_photo" in message:
                self._handle_new_chat_photo_message(chat_id)
            # At this point we don't know what message type it is, so we do nothing
            else:
                self._logger.debug("Got an unknown message. Doing nothing. Update was: %s", update)
        # Triggered when the user clicks on inline buttons
        elif "callback_query" in update:
            self._handle_callback_query(update["callback_query"], chat_id, from_id)
        # Triggered when the bot's role in a chat changes (e.g., added, removed, promoted to admin, blocked in private chat, etc.)
        elif "my_chat_member" in update:
            self._handle_my_chat_member(update["my_chat_member"], chat_id)
        else:
            self._logger.debug("Got an unknown update. Doing nothing. Update was: %s", update)

    def _handle_my_chat_member(self, my_chat_member: dict, chat_id: str) -> None:
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

    def _enroll_chat(self, chat_id: str, chat_title: str, chat_type: str, msg_id_to_reply_to: str = "") -> None:
        """Add a chat to the known chats and tell it that its permissions still have to be configured."""
        self.plugin_context.chats.add_chat(chat_id, chat_title, chat_type)
        self.plugin_context.sender.send_message(
            render_emojis(
                "{emo:info} Chat added to known chats. "
                "Before you can do anything, please go to plugin settings and edit your permissions."
            ),
            chat_id,
            reply_to_message_id=msg_id_to_reply_to,
        )

    def _handle_new_chat_title_message(self, message: dict, chat_id: str) -> None:
        self._logger.info("Chat %s changed title, updating it...", chat_id)

        chat = message["chat"]

        self.plugin_context.settings.set_chat_field(chat_id, "title", get_chat_title(chat))
        self.plugin_context.settings.save()
        self.plugin_context.frontend.update_known_chats(self.plugin_context.settings.chats)

    def _handle_new_chat_photo_message(self, chat_id: str) -> None:
        self._logger.info("Chat %s changed picture, updating it...", chat_id)

        try:

            def update_chat_picture() -> None:
                public_path = self.plugin_context.chats.save_chat_picture(chat_id)
                self.plugin_context.settings.set_chat_field(chat_id, "image", public_path)
                self.plugin_context.settings.save()
                self.plugin_context.frontend.update_known_chats(self.plugin_context.settings.chats)

            threading.Thread(target=update_chat_picture, daemon=True).start()
        except Exception:
            self._logger.exception("Caught an exception updating chat picture for chat_id %s", chat_id)

    def _handle_text_message(self, message: dict, chat_id: str, from_id: str, msg_id_to_reply_to: str) -> None:
        message_text = message["text"]
        telegram_user = message.get("from") or {}

        replied_message_id = str(message.get("reply_to_message", {}).get("message_id", ""))
        awaited_reply = (
            self.plugin_context.menu_states.get_awaited_reply(chat_id, replied_message_id)
            if replied_message_id
            else None
        )

        if awaited_reply is not None:
            self._handle_command(
                CommandContext(
                    cmd=awaited_reply.command,
                    chat_id=chat_id,
                    from_id=from_id,
                    parameter=awaited_reply.parameter_prefix + message_text,
                    msg_id_to_update=awaited_reply.msg_id_to_update,
                    msg_id_to_reply_to=msg_id_to_reply_to,
                    telegram_user=telegram_user,
                )
            )
            if awaited_reply.delete_answer_message:
                try:
                    self.plugin_context.sender.delete_message(chat_id, str(message["message_id"]))
                except Exception:
                    self._logger.debug("Could not delete the message answering %s", awaited_reply.command)
            return

        if not message_text.startswith("/"):
            self._logger.debug("Ignoring text message '%s' because it doesn't start with a slash", message_text)
            return

        # Remove bot username from commands like /command@botusername
        command = message_text.split("@")[0]

        self._handle_command(
            CommandContext(
                cmd=command,
                chat_id=chat_id,
                from_id=from_id,
                msg_id_to_reply_to=msg_id_to_reply_to,
                telegram_user=telegram_user,
            )
        )

    def _handle_callback_query(self, callback_query: dict, chat_id: str, from_id: str) -> None:
        command, _, parameter = callback_query["data"].partition("_")
        telegram_user = callback_query["from"]
        msg_id_to_update = str(callback_query.get("message", {}).get("message_id", ""))

        try:
            self._handle_command(
                CommandContext(
                    cmd=command,
                    chat_id=chat_id,
                    from_id=from_id,
                    parameter=parameter,
                    msg_id_to_update=msg_id_to_update,
                    telegram_user=telegram_user,
                )
            )
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

    def _handle_command(self, command_context: CommandContext) -> None:
        """Run a bot command.

        Args:
            command_context (CommandContext): The details of a single command invocation.
        """
        command_context.cmd = command_context.cmd.lower()

        command_definition = registry.get(command_context.cmd)
        if command_definition is None or not command_definition.takes_parameter:
            command_context.parameter = ""

        # Log received command
        self._logger.info(
            "Received command '%s' with parameter '%s' in chat '%s' from '%s'",
            command_context.cmd,
            command_context.parameter,
            command_context.chat_id,
            command_context.from_id,
        )

        # Is command  known?
        if command_definition is None:
            # we dont know the command so skip the message
            self._logger.warning("Previous command was an unknown command.")
            if not self.plugin_context.settings.no_mistake:
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:notallowed} I do not understand you!"),
                    command_context.chat_id,
                    reply_to_message_id=command_context.msg_id_to_reply_to,
                )
            return

        # Check if user is allowed to execute the command
        if permissions.is_command_allowed(
            self.plugin_context.settings, command_context.chat_id, command_context.from_id, command_context.cmd
        ):
            # Execute command
            try:
                self._commands.run_command(command_context)
            except StaleMenuError:
                self.plugin_context.menu_states.discard_menu_state(
                    command_context.chat_id, command_context.msg_id_to_update
                )
                self.plugin_context.sender.send_message(
                    render_emojis(
                        f"{{emo:attention}} The button you pressed was no longer valid. Please run {command_context.cmd} again."
                    ),
                    command_context.chat_id,
                    message_id=command_context.msg_id_to_update,
                    reply_to_message_id=command_context.msg_id_to_reply_to,
                )
            except Exception:
                self._logger.exception("Caught an exception executing command %s", command_context.cmd)
                self.plugin_context.menu_states.discard_menu_state(
                    command_context.chat_id, command_context.msg_id_to_update
                )
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:attention} Error executing your command! Please check logs."),
                    command_context.chat_id,
                    message_id=command_context.msg_id_to_update,
                    reply_to_message_id=command_context.msg_id_to_reply_to,
                )
        else:
            # User was not allowed to execute this command
            self._logger.warning("Previous command was from an unauthorized user.")
            self.plugin_context.sender.send_message(
                render_emojis("{emo:notallowed} You are not allowed to do this!"),
                command_context.chat_id,
                reply_to_message_id=command_context.msg_id_to_reply_to,
            )

    def _get_chat_and_from_ids(self, update: dict) -> tuple[str, str]:
        """Get the chat an update comes from and the user who sent it.

        Args:
            update (dict): The update as Telegram sent it.

        Returns:
            tuple[str, str]: The id of the chat, then the id of the user, empty when the update has no author.

        Raises:
            ValueError: If the update is of a type the bot does not handle.
        """
        for update_type in SUPPORTED_UPDATE_TYPES:
            if update_type in update:
                update_content = update[update_type]
                chat = update_content["message"]["chat"] if update_type == "callback_query" else update_content["chat"]
                return str(chat["id"]), str(update_content.get("from", {}).get("id", ""))

        raise ValueError(f"Unsupported update type: none of {SUPPORTED_UPDATE_TYPES} found")
