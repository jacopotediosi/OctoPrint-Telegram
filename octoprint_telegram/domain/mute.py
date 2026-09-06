class MutedChats:
    """The chats that asked to receive no notifications until the print ends."""

    def __init__(self) -> None:
        """Create the set of muted chats."""
        self._muted_chat_ids = set()

    def mute_chat(self, chat_id: str) -> None:
        """Mute a chat."""
        self._muted_chat_ids.add(chat_id)

    def unmute_chat(self, chat_id: str) -> None:
        """Unmute a chat."""
        self._muted_chat_ids.discard(chat_id)

    def unmute_all(self) -> None:
        """Unmute all chats."""
        self._muted_chat_ids.clear()

    def is_muted(self, chat_id: str) -> bool:
        """Whether a chat is muted."""
        return chat_id in self._muted_chat_ids
