import logging

from ..telegram.client import TOKEN_REGEX


class RedactingFormatter(logging.Formatter):
    """A log formatter that removes secrets from the messages it writes."""

    def format(self, record):
        try:
            formatted = super().format(record)
            return TOKEN_REGEX.sub("REDACTED", formatted)
        except Exception as e:
            return f"RedactingFormatter failed: {type(e).__name__}"
