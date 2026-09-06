import time

WINDOW_SECONDS = 5 * 60


class Enrollment:
    """The time window during which unknown chats are allowed to add themselves."""

    def __init__(self) -> None:
        """Create the enrollment window."""
        self._open_until = None

    def open(self) -> int:
        """Open the enrollment time window and return how many seconds it stays open for."""
        self._open_until = time.monotonic() + WINDOW_SECONDS
        return WINDOW_SECONDS

    def close(self) -> None:
        """Close the window immediately."""
        self._open_until = None

    @property
    def is_open(self) -> bool:
        """Whether unknown chats can be added right now."""
        return self._open_until is not None and time.monotonic() <= self._open_until

    @property
    def remaining_seconds(self) -> int:
        """The seconds the enrollment window stays open for, or 0 once it is closed."""
        if self._open_until is None:
            return 0
        return max(0, int(self._open_until - time.monotonic()))
