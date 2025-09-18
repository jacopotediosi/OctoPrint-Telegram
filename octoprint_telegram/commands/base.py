from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import TelegramPlugin


class CommandContext:
    def __init__(
        self, cmd: str, chat_id: str, from_id: str, parameter: str = "", msg_id_to_update: str = "", user: str = ""
    ):
        self.cmd = cmd
        self.chat_id = chat_id
        self.from_id = from_id
        self.parameter = parameter
        self.msg_id_to_update = msg_id_to_update
        self.user = user


class BaseCommand(ABC):
    def __init__(self, main: "TelegramPlugin"):
        self.main = main
        self._logger = main._logger.getChild("Commands")

    def __call__(self, cmd, chat_id, from_id, parameter="", msg_id_to_update="", user=""):
        context = CommandContext(cmd, chat_id, from_id, parameter, msg_id_to_update, user)
        return self.execute(context)

    @abstractmethod
    def execute(self, context: CommandContext):
        pass
