from typing_extensions import override

from .base import BaseCommand, CommandContext


class CmdStart(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        return
