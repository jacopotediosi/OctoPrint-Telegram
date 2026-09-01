from __future__ import annotations

from typing import TYPE_CHECKING

from . import registry
from .base import BaseCommand

if TYPE_CHECKING:
    from ..core.context import PluginContext


class Commands:
    """The bot commands, ready to run."""

    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up one runnable instance of every declared command.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        self._commands: dict[str, BaseCommand] = {
            command.name: command.implementation(plugin_context) for command in registry.COMMAND_DEFINITIONS
        }

    def run_command(
        self,
        command: str,
        chat_id: str,
        from_id: str,
        parameter: str,
        msg_id_to_update: str,
        msg_id_to_reply_to: str,
        user: str,
    ) -> None:
        """Run a command by its textual name.

        Args:
            command (str): The command to run.
            chat_id (str): The chat the command was sent from.
            from_id (str): The id of the user who sent the command.
            parameter (str): The parameter the command was invoked with.
            msg_id_to_update (str): The message to replace with the answer, instead of sending a new one.
            msg_id_to_reply_to (str): The message the answer is a reply to.
            user (str): The name of the user who sent the command.

        Raises:
            KeyError: If the command doesn't exist.
        """
        return self._commands[command](command, chat_id, from_id, parameter, msg_id_to_update, msg_id_to_reply_to, user)
