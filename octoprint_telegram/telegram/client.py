from __future__ import annotations

import json
import logging
import re
import traceback
from typing import TYPE_CHECKING, Any

import requests

from .enums import HttpMethod

if TYPE_CHECKING:
    from ..core.settings import Settings

TOKEN_REGEX = re.compile(r"[\d]{8,10}:[\w-]{35}")

API_BASE_URL = "https://api.telegram.org"


class TelegramRequestError(Exception):
    """Raised when a call to the Telegram Bot API does not return a usable response."""

    def __init__(self, message: str, telegram_response_text: str = "") -> None:
        """Set up the error.

        Args:
            message (str): The description of what went wrong.
            telegram_response_text (str, optional): The raw body Telegram answered with.
        """
        super().__init__(message)
        self.telegram_response_text = telegram_response_text


class TelegramClient:
    """The Telegram Bot API, for the bot the configured token belongs to."""

    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        """Set up the access to the Telegram Bot API.

        Args:
            settings (Settings): The plugin settings.
            logger (logging.Logger): The logger to write to.
        """
        self._settings = settings
        self._logger = logger.getChild("TelegramClient")
        self._token = None

    ##########
    ### Connection
    ##########

    def connect(self, token: str) -> None:
        """Start addressing the bot the token belongs to."""
        self._token = token

    def disconnect(self) -> None:
        """Stop addressing any bot."""
        self._token = None

    @property
    def is_connected(self) -> bool:
        """Whether a bot is currently being addressed."""
        return bool(self._token)

    ##########
    ### Requests
    ##########

    def _get_proxies(self) -> dict:
        return {"http": self._settings.http_proxy, "https": self._settings.https_proxy}

    def send_request(self, endpoint: str, method: HttpMethod, token: str | None = None, **kwargs: Any) -> dict:
        """Call a Telegram Bot API method and return its decoded response.

        Args:
            endpoint (str): The API method to call, e.g. "sendMessage".
            method (HttpMethod): The HTTP method to use.
            token (str, optional): The bot token to use instead of the connected one.
            **kwargs: Additional arguments passed to the underlying requests library
                    (e.g., 'data', 'params', 'files').

        Returns:
            dict: The JSON-decoded response from Telegram, guaranteed to contain 'ok': True.

        Raises:
            TelegramRequestError: If the request fails, the response is invalid, or the Telegram API returns an error.
        """
        if token is None:
            token = self._token

        url = f"{API_BASE_URL}/bot{token}/{endpoint}"

        default_kwargs = {
            "allow_redirects": False,
            "timeout": 60,
            "proxies": self._get_proxies(),
        }
        request_kwargs: dict[str, Any] = {**default_kwargs, **kwargs}

        loggable_kwargs = {k: ("<binary data>" if k == "files" else v) for k, v in request_kwargs.items()}
        self._logger.debug("Sending Telegram request: method=%s, url=%s, kwargs=%s", method.value, url, loggable_kwargs)

        try:
            response = requests.request(method.value, url, **request_kwargs)
            self._logger.debug("Received Telegram response: %s", response.text)
        except Exception:
            raise TelegramRequestError(
                f"Caught an exception sending telegram request. Traceback: {traceback.format_exc()}."
            )

        if not response.ok:
            raise TelegramRequestError(
                f"Telegram request responded with code {response.status_code}. Response was: {response.text}.",
                response.text,
            )

        content_type = response.headers.get("content-type", "")
        if content_type != "application/json":
            raise TelegramRequestError(
                f"Unexpected Content-Type. Expected: application/json. It was: {content_type}. Response was: {response.text}.",
                response.text,
            )

        try:
            json_data = response.json()
        except Exception:
            raise TelegramRequestError(
                f"Failed to parse telegram response to json. Response was: {response.text}.", response.text
            )

        if not json_data.get("ok", False):
            raise TelegramRequestError(
                f"Response didn't include 'ok:true'. Response was: {response.text}.", response.text
            )

        return json_data

    ##########
    ### Bot
    ##########

    def get_bot_username(self, token: str | None = None) -> str:
        """The @username of the bot a token belongs to.

        Args:
            token (str, optional): The bot token to use instead of the connected one.

        Returns:
            str: The @username of the bot.

        Raises:
            TelegramRequestError: If the request fails, the response is invalid, or the Telegram API returns an error.
        """
        json_data = self.send_request("getMe", HttpMethod.GET, token=token)
        return f"@{json_data['result']['username']}"

    def set_bot_commands(self, commands: list[dict]) -> None:
        """Publish the command list users see in their Telegram client."""
        self.send_request("setMyCommands", HttpMethod.POST, data={"commands": json.dumps(commands)})

    ##########
    ### Files
    ##########

    def download_file(self, file_id: str) -> bytes:
        """Download the content of a file from the Telegram servers."""
        self._logger.debug("Requesting file with id %s", file_id)

        json_data = self.send_request("getFile", HttpMethod.GET, data={"file_id": file_id})

        file_path = json_data["result"]["file_path"]
        file_url = f"{API_BASE_URL}/file/bot{self._token}/{file_path}"

        self._logger.info("Downloading file: %s", file_url)

        file_req = requests.get(file_url, proxies=self._get_proxies())
        file_req.raise_for_status()

        return file_req.content
