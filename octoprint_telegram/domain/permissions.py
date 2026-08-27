from __future__ import annotations

from typing import TYPE_CHECKING

from ..commands import registry
from .chats import is_group_or_channel

if TYPE_CHECKING:
    from ..core.settings import Settings


def is_command_allowed(settings: Settings, chat_id: str, from_id: str, command: str) -> bool:
    """Whether a command may run in a chat, for the user who sent it."""
    # If no command, nothing to allow
    if not command:
        return False

    # Commands everyone is allowed to use (e.g., /help)
    command_definition = registry.get(command)
    if command_definition is not None and command_definition.available_to_everyone:
        return True

    chat_settings = settings.chat(chat_id) or {}
    chat_accepts_commands = chat_settings.get("accept_commands", False)
    chat_accepts_this_command = chat_settings.get("commands", {}).get(command, False)
    chat_allows_users = chat_settings.get("allow_users", False)

    # Commands allowed for all chat members (both in private chat and in groups)
    if chat_accepts_commands and chat_accepts_this_command:
        return True

    from_settings = settings.chat(from_id) or {}
    from_accepts_commands = from_settings.get("accept_commands", False)
    from_accepts_this_command = from_settings.get("commands", {}).get(command, False)

    # User personal permissions within groups
    return bool(
        is_group_or_channel(chat_id) and chat_allows_users and from_accepts_commands and from_accepts_this_command
    )
