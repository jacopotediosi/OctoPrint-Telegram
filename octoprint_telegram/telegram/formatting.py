from __future__ import annotations

import html
import re

from .enums import Markup


def escape_text(text: str, markup: Markup) -> str:
    """Escape the characters Telegram reads as markup.

    Args:
        text (str): The text to escape.
        markup (Markup): The markup Telegram parses in the text.

    Returns:
        str: The escaped text.
    """
    if markup is Markup.HTML:
        return html.escape(text)
    if markup is Markup.MARKDOWN:
        return _escape_markdown(text, 1)
    if markup is Markup.MARKDOWN_V2:
        return _escape_markdown(text, 2)
    return text


def _escape_markdown(text: str, version: int = 1, entity_type: str | None = None) -> str:
    """Helper function to escape telegram markup symbols.

    Copied from python-telegram-bot/python-telegram-bot

    .. versionchanged:: 20.3
        Custom emoji entity escaping is now supported.

    Args:
        text (:obj:`str`): The text.
        version (:obj:`int` | :obj:`str`): Use to specify the version of telegrams Markdown.
            Either ``1`` or ``2``. Defaults to ``1``.
        entity_type (:obj:`str`, optional): For the entity types
            :tg-const:`telegram.MessageEntity.PRE`, :tg-const:`telegram.MessageEntity.CODE` and
            the link part of :tg-const:`telegram.MessageEntity.TEXT_LINK` and
            :tg-const:`telegram.MessageEntity.CUSTOM_EMOJI`, only certain characters need to be
            escaped in :tg-const:`telegram.constants.ParseMode.MARKDOWN_V2`. See the `official API
            documentation <https://core.telegram.org/bots/api#formatting-options>`_ for details.
            Only valid in combination with ``version=2``, will be ignored else.

    Returns:
        :obj:`str`: Escaped text.

    Raises:
        ValueError: If the Markdown version is neither ``1`` nor ``2``.
    """
    if int(version) == 1:
        escape_chars = r"_*`["
    elif int(version) == 2:
        if entity_type in ["pre", "code"]:
            escape_chars = r"\`"
        elif entity_type in ["text_link", "custom_emoji"]:
            escape_chars = r"\)"
        else:
            escape_chars = r"\_*[]()~`>#+-=|{}.!"
    else:
        raise ValueError("Markdown version must be either 1 or 2!")

    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)
