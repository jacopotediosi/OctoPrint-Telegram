from .base import BaseCommand, CommandContext


class CmdStatus(BaseCommand):
    def execute(self, context: CommandContext):
        if not self.main._printer.is_operational():
            self.main.on_event("StatusNotConnected", {}, chatID=context.chat_id)
        elif self.main._printer.is_printing() or self.main._printer.is_pausing() or self.main._printer.is_paused():
            self.main.on_event("StatusPrinting", {}, chatID=context.chat_id)
        else:
            self.main.on_event("StatusNotPrinting", {}, chatID=context.chat_id)
