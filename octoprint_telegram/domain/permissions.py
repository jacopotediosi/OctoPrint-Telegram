from __future__ import annotations

from typing import TYPE_CHECKING

from ..commands import registry
from .chats import is_group_or_channel

if TYPE_CHECKING:
    from ..core.settings import Settings


def is_command_allowed_to_all_members(settings: Settings, chat_id: str, command: str) -> bool:
    """Whether every member of a chat may run a command, both in private chats and in groups."""
    chat_settings = settings.chat(chat_id) or {}
    return bool(chat_settings.get("accept_commands", False) and chat_settings.get("commands", {}).get(command, False))


def is_command_allowed_individually(settings: Settings, chat_id: str, from_id: str, command: str) -> bool:
    """Whether a user may run a command in a group or channel thanks to their personal permissions."""
    chat_settings = settings.chat(chat_id) or {}
    from_settings = settings.chat(from_id) or {}
    return bool(
        is_group_or_channel(chat_id)
        and chat_settings.get("allow_users", False)
        and from_settings.get("accept_commands", False)
        and from_settings.get("commands", {}).get(command, False)
    )


def is_command_allowed(settings: Settings, chat_id: str, from_id: str, command: str) -> bool:
    """Whether a command may run in a chat, for the user who sent it."""
    # If no command, nothing to allow
    if not command:
        return False

    # Commands everyone is allowed to use (e.g., /help)
    command_definition = registry.get(command)
    if command_definition is not None and command_definition.available_to_everyone:
        return True

    return is_command_allowed_to_all_members(settings, chat_id, command) or is_command_allowed_individually(
        settings, chat_id, from_id, command
    )
