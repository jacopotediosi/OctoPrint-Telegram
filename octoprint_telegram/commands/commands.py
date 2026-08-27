from __future__ import annotations

from typing import TYPE_CHECKING

from . import registry
from .base import BaseCommand

if TYPE_CHECKING:
    from ..core.context import PluginContext


class Commands:
    """The bot commands, ready to run."""

    def __init__(self, plugin_context: PluginContext):
        self._commands: dict[str, BaseCommand] = {
            command.name: command.implementation(plugin_context) for command in registry.COMMAND_DEFINITIONS
        }

    def run_command(
        self, command: str, chat_id: str, from_id: str, parameter: str, msg_id_to_update: str, user: str
    ) -> None:
        """
        Run a command by its textual name.

        Raises:
            KeyError: If the command doesn't exist.
        """
        return self._commands[command](command, chat_id, from_id, parameter, msg_id_to_update, user)
