from __future__ import annotations

from typing import TYPE_CHECKING

from . import registry
from .base import BaseCommand, CommandContext

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

    def run_command(self, command_context: CommandContext) -> None:
        """Run a bot command.

        Args:
            command_context (CommandContext): The details of a single command invocation.

        Raises:
            KeyError: If the command doesn't exist.
        """
        self._commands[command_context.cmd].execute(command_context)
