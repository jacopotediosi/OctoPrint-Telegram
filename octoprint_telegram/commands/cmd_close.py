from typing_extensions import override

from .base import BaseCommand, CommandContext


class CmdClose(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        # According to https://core.telegram.org/bots/api#deletemessage:
        # - A message can only be deleted if it was sent less than 48 hours ago.
        # The try-except block handles this condition.
        try:
            if command_context.msg_id_to_update:
                self.plugin_context.sender.delete_message(command_context.chat_id, command_context.msg_id_to_update)
                self.plugin_context.menu_states.discard_menu_state(
                    command_context.chat_id, command_context.msg_id_to_update
                )
        except Exception:
            pass
