import logging
import re
import traceback
from typing import Optional

import requests

_logger = logging.getLogger("octoprint.plugins.telegram").getChild("TelegramUtils")


class TelegramUtils:
    def __init__(self, main):
        self.main = main

    def get_proxies(self):
        http_proxy = self.main._settings.get(["http_proxy"])
        https_proxy = self.main._settings.get(["https_proxy"])
        return {"http": http_proxy, "https": https_proxy}

    def send_telegram_request(self, url, method, **kwargs):
        """
        Sends a request to the Telegram Bot API and returns the parsed JSON response.

        This method handles request execution, error checking, and JSON decoding.
        It raises an exception if the HTTP request fails, returns an unexpected status,
        an invalid content type, or if the Telegram API indicates an error.

        Args:
            url (str): The full Telegram API URL to call.
            method (str): The HTTP method to use ("get" or "post").
            **kwargs: Additional arguments passed to the underlying requests library
                    (e.g., 'data', 'params', 'files').

        Returns:
            dict: The JSON-decoded response from Telegram, guaranteed to contain 'ok': True.

        Raises:
            ValueError: If the HTTP method is not "get" or "post".
            Exception: If the request fails, the response is invalid, or the Telegram API returns an error.
        """
        method = method.lower()
        if method not in {"get", "post"}:
            raise ValueError(f"Unsupported HTTP method: {method}")

        default_kwargs = {
            "allow_redirects": False,
            "timeout": 60,
            "proxies": self.get_proxies(),
        }
        request_kwargs = {**default_kwargs, **kwargs}

        loggable_kwargs = {k: ("<binary data>" if k == "files" else v) for k, v in request_kwargs.items()}
        _logger.debug(f"Sending Telegram request: method={method}, url={url}, kwargs={loggable_kwargs}.")

        try:
            response = requests.request(method, url, **request_kwargs)
            _logger.debug(f"Received Telegram response: {response.text}.")
        except Exception:
            raise Exception(f"Caught an exception sending telegram request. Traceback: {traceback.format_exc()}.")

        if not response.ok:
            raise Exception(
                f"Telegram request responded with code {response.status_code}. Response was: {response.text}."
            )

        content_type = response.headers.get("content-type", "")
        if content_type != "application/json":
            raise Exception(
                f"Unexpected Content-Type. Expected: application/json. It was: {content_type}. Response was: {response.text}."
            )

        try:
            json_data = response.json()

            if not json_data.get("ok", False):
                raise Exception(f"Response didn't include 'ok:true'. Response was: {json_data}.")

            return json_data
        except Exception:
            raise Exception(f"Failed to parse telegram response to json. Response was: {response.text}.")


def is_group_or_channel(chat_id):
    return int(chat_id) < 0


def escape_markdown(text: str, version: int = 1, entity_type: Optional[str] = None) -> str:
    """
    Copied from python-telegram-bot/python-telegram-bot

    Helper function to escape telegram markup symbols.

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
