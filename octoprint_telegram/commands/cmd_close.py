from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdClose(BaseCommand):
    def execute(self, context: CommandContext):
        # According to https://core.telegram.org/bots/api#deletemessage:
        # - A message can only be deleted if it was sent less than 48 hours ago.
        # The try-except block handles this condition.
        try:
            if context.msg_id_to_update:
                self.main.telegram_utils.send_telegram_request(
                    f"{self.main.bot_url}/deleteMessage",
                    "post",
                    data=dict(chat_id=context.chat_id, message_id=context.msg_id_to_update),
                )
        except Exception:
            pass
