from __future__ import annotations

import threading
from typing import TypeVar

import pylru


class MenuState:
    """What a command remembers about a menu it has drawn."""


class ReplyPrompt(MenuState):
    """A message asking the user to answer with the parameter of a command."""

    def __init__(self, command: str) -> None:
        """Set up the prompt.

        Args:
            command (str): The command the answer is the parameter of.
        """
        self.command = command


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
            menu_state = self._menu_states.get((chat_id, message_id))
            return menu_state if isinstance(menu_state, menu_state_type) else None

    def set_menu_state(self, chat_id: str, message_id: str, menu_state: MenuState) -> None:
        """Store the state of the menu shown in a message."""
        with self._lock:
            self._menu_states[(chat_id, message_id)] = menu_state

    def discard_menu_state(self, chat_id: str, message_id: str) -> None:
        """Forget the state of the menu shown in a message."""
        with self._lock:
            key = (chat_id, message_id)
            if key in self._menu_states:
                del self._menu_states[key]
