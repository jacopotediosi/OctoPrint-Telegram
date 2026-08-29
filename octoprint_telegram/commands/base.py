from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.context import PluginContext


class CommandContext:
    def __init__(
        self, cmd: str, chat_id: str, from_id: str, parameter: str = "", msg_id_to_update: str = "", user: str = ""
    ) -> None:
        self.cmd = cmd
        self.chat_id = chat_id
        self.from_id = from_id
        self.parameter = parameter
        self.msg_id_to_update = msg_id_to_update
        self.user = user


class BaseCommand(ABC):
    def __init__(self, plugin_context: PluginContext) -> None:
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
        command_context = CommandContext(cmd, chat_id, from_id, parameter, msg_id_to_update, user)
        return self.execute(command_context)

    @abstractmethod
    def execute(self, command_context: CommandContext) -> None:
        pass
