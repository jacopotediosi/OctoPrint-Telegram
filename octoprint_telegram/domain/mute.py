class MutedChats:
    """The chats that asked to receive no notifications until the print ends."""

    def __init__(self):
        self._muted_chat_ids = set()

    def mute_chat(self, chat_id: str) -> None:
        self._muted_chat_ids.add(chat_id)

    def unmute_chat(self, chat_id: str) -> None:
        self._muted_chat_ids.discard(chat_id)

    def unmute_all(self) -> None:
        self._muted_chat_ids.clear()

    def is_muted(self, chat_id: str) -> bool:
        return chat_id in self._muted_chat_ids
