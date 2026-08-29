from __future__ import annotations

import hashlib


# Telegram limits callback data to 64 bytes, so identifiers carried in it are
# hashed and truncated to fit alongside the rest of the callback.
def hash_value(value: str | int, length: int = 32) -> str:
    """A short, stable identifier for a value, usable inside callback data."""
    return hashlib.md5(str(value).encode()).hexdigest()[:length]
