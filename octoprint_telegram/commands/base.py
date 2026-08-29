from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.context import PluginContext


class CommandContext:
    def __init__(
        self, cmd: str, chat_id: str, from_id: str, parameter: str = "", msg_id_to_update: str = "", user: str = ""
    ) -> None:
        """Set up the details of a single command invocation.

        Args:
            cmd (str): The command being run.
            chat_id (str): The chat the command was sent from.
            from_id (str): The id of the user who sent the command.
            parameter (str, optional): The parameter the command was invoked with.
            msg_id_to_update (str, optional): The message to replace with the answer, instead of sending a new one.
            user (str, optional): The name of the user who sent the command.
        """
        self.cmd = cmd
        self.chat_id = chat_id
        self.from_id = from_id
        self.parameter = parameter
        self.msg_id_to_update = msg_id_to_update
        self.user = user


class BaseCommand(ABC):
    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up a bot command.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("Commands")

    def __call__(
        self,
        cmd: str,
        chat_id: str,
        from_id: str,
        parameter: str = "",
        msg_id_to_update: str = "",
        user: str = "",
    ) -> None:
        """Run the command on a single invocation.

        Args:
            cmd (str): The command being run.
            chat_id (str): The chat the command was sent from.
            from_id (str): The id of the user who sent the command.
            parameter (str, optional): The parameter the command was invoked with.
            msg_id_to_update (str, optional): The message to replace with the answer, instead of sending a new one.
            user (str, optional): The name of the user who sent the command.
        """
        command_context = CommandContext(cmd, chat_id, from_id, parameter, msg_id_to_update, user)
        return self.execute(command_context)

    @abstractmethod
    def execute(self, command_context: CommandContext) -> None:
        """Run the command.

        Args:
            command_context (CommandContext): The details of a single command invocation.
        """
