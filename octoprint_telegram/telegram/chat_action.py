from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from .enums import ChatAction, HttpMethod

if TYPE_CHECKING:
    from .client import TelegramClient

# A chat action shown in Telegram expires after about five seconds
CHAT_ACTION_REFRESH_SECONDS = 4.5


@contextmanager
def chat_action(
    telegram_client: TelegramClient, chat_id: str, action: ChatAction, logger: logging.Logger
) -> Iterator[None]:
    """Show an activity indicator in the chat for as long as the block runs.

    Args:
        telegram_client (TelegramClient): The client the indicator is sent through.
        chat_id (str): The chat to show the indicator in.
        action (ChatAction): The activity to show.
        logger (logging.Logger): The logger failures are reported to.
    """
    if not chat_id:
        yield
        return

    stop_event = threading.Event()

    def _loop() -> None:
        try:
            while not stop_event.is_set():
                telegram_client.send_request(
                    "sendChatAction",
                    HttpMethod.GET,
                    params={"chat_id": chat_id, "action": action.value},
                    timeout=5,
                )
                stop_event.wait(CHAT_ACTION_REFRESH_SECONDS)
        except Exception:
            logger.exception("Exception in chat_action loop")

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()

    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=2)
