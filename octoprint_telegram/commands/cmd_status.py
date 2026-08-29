from .base import BaseCommand, CommandContext


class CmdStatus(BaseCommand):
    def execute(self, command_context: CommandContext) -> None:
        if not self.plugin_context.printer.is_operational():
            self.plugin_context.notifications.send_notification(
                "StatusNotConnected", {}, chat_id=command_context.chat_id
            )
        elif (
            self.plugin_context.printer.is_printing()
            or self.plugin_context.printer.is_pausing()
            or self.plugin_context.printer.is_paused()
        ):
            self.plugin_context.notifications.send_notification("StatusPrinting", {}, chat_id=command_context.chat_id)
        else:
            self.plugin_context.notifications.send_notification(
                "StatusNotPrinting", {}, chat_id=command_context.chat_id
            )
