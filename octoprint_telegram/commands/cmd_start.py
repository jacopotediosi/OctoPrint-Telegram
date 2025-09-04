from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdStart(BaseCommand):
    def execute(self, context: CommandContext):
        return
