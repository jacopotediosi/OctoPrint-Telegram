from __future__ import annotations

import _string  # type: ignore
import string
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from typing_extensions import override

from ..telegram.formatting import escape_text
from .variables import cached_property

if TYPE_CHECKING:
    import logging

    from ..telegram import Markup
    from .variables import NotificationVariables


class _MarkupEscapedValue:
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

    def __getitem__(self, key: str | int) -> _MarkupEscapedValue:
        """Navigate into the wrapped value, keeping it wrapped.

        Args:
            key (str | int): The dictionary key or the list index to read.

        Returns:
            _MarkupEscapedValue: The value found, or a "[ERROR]" placeholder if it cannot be read.
        """
        try:
            # Support dictionary/list navigation
            return _MarkupEscapedValue(self._value[key], self._markup, self._logger)
        except Exception:
            self._logger.exception("Caught an exception navigating dict/list")
            # Return an error placeholder if attempting to access non-existent key or invalid index
            return _MarkupEscapedValue("[ERROR]", self._markup, self._logger)

    def __str__(self) -> str:
        """Render the wrapped value, escaped for the markup.

        Returns:
            str: The escaped text.
        """
        # Apply markup escaping only at final string conversion
        return escape_text(str(self._value), self._markup)

    def __repr__(self) -> str:
        """Render the wrapped value, escaped for the markup.

        Returns:
            str: The escaped text.
        """
        return str(self)

    def __format__(self, format_spec: str) -> str:
        """Render the wrapped value formatted as the placeholder asks, escaped for the markup.

        Args:
            format_spec (str): The format specification written in the placeholder.

        Returns:
            str: The escaped text, or a "[ERROR]" placeholder if the value cannot be formatted that way.
        """
        try:
            # Apply the format specification before escaping, so the escaping does not alter it
            return escape_text(format(self._value, format_spec), self._markup)
        except Exception:
            self._logger.exception("Caught an exception formatting a notification variable")
            return escape_text("[ERROR]", self._markup)


class _UnknownPlaceholder:
    """A placeholder that names no template variable, rendered as it was written."""

    def __init__(self, expression: str, markup: Markup) -> None:
        self._expression = expression
        self._markup = markup

    def __getitem__(self, key: str | int) -> _UnknownPlaceholder:
        return _UnknownPlaceholder(f"{self._expression}[{key}]", self._markup)

    def __str__(self) -> str:
        return escape_text("{" + self._expression + "}", self._markup)

    def __repr__(self) -> str:
        return str(self)

    def __format__(self, format_spec: str) -> str:
        expression = f"{self._expression}:{format_spec}" if format_spec else self._expression
        return escape_text("{" + expression + "}", self._markup)


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

    def __getitem__(self, key: str) -> _MarkupEscapedValue | _UnknownPlaceholder:
        """Resolve a placeholder to the value of the template variable it names.

        Args:
            key (str): The name written in the placeholder.

        Returns:
            _MarkupEscapedValue | _UnknownPlaceholder: The markup escaped value of the variable, the placeholder
                as it was written when the name is not a template variable, or a "[ERROR]" placeholder when
                reading the variable failed.
        """
        # If variable is not in the allowed names, return it as a literal
        if key not in self._allowed_names:
            return _UnknownPlaceholder(key, self._markup)

        # Get the lazy value and wrap it with markup escaping
        try:
            return _MarkupEscapedValue(getattr(self._variables, key), self._markup, self._logger)
        except Exception:
            self._logger.exception("Caught an exception getting the notification variable %s", key)
            # Return an error placeholder if getting the notification variable raised an exception
            return _MarkupEscapedValue("[ERROR]", self._markup, self._logger)


class _TemplateFormatter(string.Formatter):
    """The formatter resolving every placeholder of a template through its context."""

    def __init__(self, markup: Markup) -> None:
        super().__init__()
        self._markup = markup

    @override
    def get_field(self, field_name: str, args: Sequence[Any], kwargs: Mapping[str, Any]) -> tuple[Any, str]:
        """Resolve a placeholder to its value, navigating into it with keys and indexes."""
        _first, rest = _string.formatter_field_name_split(field_name)

        # Dot navigation is refused: reading attributes would escape the template variables, allowing template injection
        if any(is_attribute for is_attribute, _element in rest):
            return _UnknownPlaceholder(field_name, self._markup), field_name

        return super().get_field(field_name, args, kwargs)

    @override
    def get_value(
        self, key: str | int, args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> _MarkupEscapedValue | _UnknownPlaceholder:
        # Positional placeholders arrive as integers
        return kwargs[key if isinstance(key, str) else str(key)]


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
    return _TemplateFormatter(markup).vformat(template, (), _TemplateContext(variables, markup, logger))
