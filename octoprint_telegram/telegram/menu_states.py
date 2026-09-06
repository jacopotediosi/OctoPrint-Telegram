from __future__ import annotations

import threading
from typing import TypeVar

import pylru


class MenuState:
    """What a command remembers about a menu it has drawn."""


class AwaitedReply:
    """The command that an answer to a message runs."""

    def __init__(
        self,
        command: str,
        parameter_prefix: str = "",
        msg_id_to_update: str = "",
        delete_answer_message: bool = False,
    ) -> None:
        """Set up the command an answer runs.

        Args:
            command (str): The command the answer runs.
            parameter_prefix (str, optional): What the answer is appended to, to build the parameter of the command.
            msg_id_to_update (str, optional): The message the answer replaces, instead of sending a new one.
            delete_answer_message (bool, optional): Remove the message carrying the answer from the chat, once the
                command has run.
        """
        self.command = command
        self.parameter_prefix = parameter_prefix
        self.msg_id_to_update = msg_id_to_update
        self.delete_answer_message = delete_answer_message


T = TypeVar("T", bound=MenuState)


class StaleMenuError(Exception):
    """Raised when the menu a pressed button belongs to is not known."""


class MenuStates:
    """The state of every menu the bot is currently showing."""

    def __init__(self, max_entries: int = 1000) -> None:
        """Set up the store of the menu states.

        Args:
            max_entries (int, optional): The number of menu states kept at the same time.
        """
        self._menu_states = pylru.lrucache(max_entries)
        self._lock = threading.RLock()

    def get_menu_state(self, chat_id: str, message_id: str, menu_state_type: type[T]) -> T | None:
        """The state of the menu shown in a message, or None if the message has no state of that type."""
        with self._lock:
            menu_state, _ = self._menu_states.get((chat_id, message_id), (None, None))
            return menu_state if isinstance(menu_state, menu_state_type) else None

    def get_awaited_reply(self, chat_id: str, message_id: str) -> AwaitedReply | None:
        """The command an answer to a message runs, or None if the message asks for no answer."""
        with self._lock:
            _, awaited_reply = self._menu_states.get((chat_id, message_id), (None, None))
            return awaited_reply

    def set_menu_state(
        self,
        chat_id: str,
        message_id: str,
        menu_state: MenuState | None,
        awaited_reply: AwaitedReply | None = None,
    ) -> None:
        """Store the state of the menu shown in a message, and the command an answer to it runs."""
        with self._lock:
            self._menu_states[(chat_id, message_id)] = (menu_state, awaited_reply)

    def discard_menu_state(self, chat_id: str, message_id: str) -> None:
        """Forget the state of the menu shown in a message."""
        with self._lock:
            key = (chat_id, message_id)
            if key in self._menu_states:
                del self._menu_states[key]
