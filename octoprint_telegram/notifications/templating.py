from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..telegram.formatting import escape_text
from .variables import cached_property

if TYPE_CHECKING:
    import logging

    from ..telegram import Markup
    from .variables import NotificationVariables


class MarkupEscapedValue:
    """Wrapper for template variable values that applies markup escaping at string conversion time.

    This ensures that escaping happens AFTER template variable resolution and dictionary/list
    navigation is complete. This allows users to write templates like {status[job][user]}
    where the escaping is applied only to the final resolved value, not to intermediate
    dictionary keys during navigation.

    The wrapper maintains the markup context and applies the appropriate escaping
    (HTML, Markdown, MarkdownV2) only when the final value is converted to string.
    """

    def __init__(
        self,
        value: Any,  # noqa: ANN401
        markup: Markup,
        logger: logging.Logger,
    ) -> None:
        """Set up the markup escaping wrapper around a template variable value.

        Args:
            value (Any): The value to wrap.
            markup (Markup): The markup Telegram parses in the text.
            logger (logging.Logger): The logger to write to.
        """
        self._value = value
        self._markup = markup
        self._logger = logger

    def __getitem__(self, key: str | int) -> MarkupEscapedValue:
        """Navigate into the wrapped value, keeping it wrapped.

        Args:
            key (str | int): The dictionary key or the list index to read.

        Returns:
            MarkupEscapedValue: The value found, or a "[ERROR]" placeholder if it cannot be read.
        """
        try:
            # Support dictionary/list navigation
            return MarkupEscapedValue(self._value[key], self._markup, self._logger)
        except Exception:
            self._logger.exception("Caught an exception navigating dict/list")
            # Return an error placeholder if attempting to access non-existent key or invalid index
            return MarkupEscapedValue("[ERROR]", self._markup, self._logger)

    def __str__(self) -> str:
        """Render the wrapped value, escaped for the markup.

        Returns:
            str: The escaped text.
        """
        # Apply markup escaping only at final string conversion
        return escape_text(str(self._value), self._markup)


class _TemplateContext(dict):
    """Secure context for template variable access.

    Only the notification variables decorated with `@cached_property` can be accessed from templates.
    Unknown or not allowed variables are returned as literal placeholders.
    """

    def __init__(self, variables: NotificationVariables, markup: Markup, logger: logging.Logger) -> None:
        self._variables = variables
        self._markup = markup
        self._logger = logger

        # Only variables decorated with @cached_property are allowed
        self._allowed_names = {
            name for name, attribute in type(variables).__dict__.items() if isinstance(attribute, cached_property)
        }

    def __getitem__(self, key: str) -> MarkupEscapedValue | str:
        """Resolve a placeholder to the value of the template variable it names.

        Args:
            key (str): The name written in the placeholder.

        Returns:
            MarkupEscapedValue | str: The markup escaped value of the variable, the placeholder itself when the
                name is not a template variable, or "[ERROR]" when reading the variable failed.
        """
        # If variable is not in the allowed names, return it as a literal
        if key not in self._allowed_names:
            return "{" + key + "}"

        # Get the lazy value and wrap it with markup escaping
        try:
            return MarkupEscapedValue(getattr(self._variables, key), self._markup, self._logger)
        except Exception:
            self._logger.exception("Caught an exception getting the notification variable %s", key)
            # Return an error placeholder if getting the notification variable raised an exception
            return "[ERROR]"


def render(template: str, variables: NotificationVariables, markup: Markup, logger: logging.Logger) -> str:
    """Fill a notification template with the values of its variables, escaped for the given markup.

    Placeholders that name no variable are left in the text as they were written.

    Args:
        template (str): The notification text.
        variables (NotificationVariables): The values the placeholders are filled with.
        markup (Markup): The markup Telegram parses in the text.
        logger (logging.Logger): The logger to write to.

    Returns:
        str: The filled template.
    """
    return template.format_map(_TemplateContext(variables, markup, logger))
