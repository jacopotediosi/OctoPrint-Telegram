from __future__ import annotations

import copy
import io
import logging
import os
import time
from typing import TYPE_CHECKING, Callable

from PIL import Image

from ..telegram import ChatType, HttpMethod

if TYPE_CHECKING:
    from ..core.frontend import Frontend
    from ..core.settings import Settings
    from ..telegram.client import TelegramClient

# Dummy element to avoid bug https://github.com/OctoPrint/OctoPrint/issues/5177
PLACEHOLDER_CHAT_ID = "zBOTTOMOFCHATS"

PICTURE_SIZE = (40, 40)


def is_group_or_channel(chat_id) -> bool:
    """Whether a chat id belongs to a group or a channel rather than to a single user."""
    return int(chat_id) < 0


def get_chat_title(chat: dict) -> str:
    """The name to show for a chat, taken from the chat as Telegram describes it."""
    if chat.get("type") == ChatType.PRIVATE.value:
        name_parts = []

        first_name = chat.get("first_name")
        last_name = chat.get("last_name")
        username = chat.get("username")

        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
        if full_name:
            name_parts.append(full_name)

        if username:
            name_parts.append(f"@{username}")

        return " - ".join(name_parts) if name_parts else "UNKNOWN"

    return chat.get("title", "UNKNOWN")


class Chats:
    """The chats the bot knows about."""

    def __init__(
        self,
        settings: Settings,
        telegram_client: TelegramClient,
        frontend: Frontend,
        data_folder: str,
        build_new_chat_settings: Callable[[], dict],
        logger: logging.Logger,
    ):
        self._settings = settings
        self._telegram_client = telegram_client
        self._frontend = frontend
        self._data_folder = data_folder
        self._build_new_chat_settings = build_new_chat_settings
        self._logger = logger.getChild("Chats")

    @property
    def all_chats(self) -> dict[str, dict]:
        """Every known chat, keyed by chat id."""
        return {k: v for k, v in self._settings.chats.items() if k != PLACEHOLDER_CHAT_ID}

    def get_chat(self, chat_id: str) -> dict | None:
        """Settings of a single chat, or None if the chat is unknown."""
        return self._settings.chat(chat_id)

    def get_chats_subscribed_to(self, event: str) -> list[str]:
        """
        The ids of the known chats that receive the notifications of an event.

        Args:
            event (str): The event the chats are subscribed to.
        """
        return [
            str(chat_id)
            for chat_id, chat_settings in self.all_chats.items()
            if chat_settings.get("send_notifications", False) and chat_settings.get("notifications", {}).get(event)
        ]

    def add_chat(self, chat_id: str, chat_title: str, chat_type: str) -> None:
        """Add a chat to the known chats."""
        self._logger.info("Adding new chat %s to known chats", chat_id)

        new_chat_settings = copy.deepcopy(self._build_new_chat_settings())
        new_chat_settings["type"] = chat_type
        new_chat_settings["title"] = chat_title
        new_chat_settings["image"] = self.save_chat_picture(chat_id)

        settings_chats = self._settings.chats
        settings_chats[chat_id] = new_chat_settings
        self._settings.chats = settings_chats
        self._settings.save()

        self._frontend.update_known_chats(self._settings.chats)

    def remove_chat(self, chat_id: str) -> None:
        """Remove a chat from the known chats."""
        self._logger.info("Removing chat %s from known chats", chat_id)

        try:
            os.remove(self._chat_picture_path(chat_id))
        except OSError:
            pass

        self._settings.remove_chat(chat_id)
        self._settings.save()

        self._frontend.update_known_chats(self._settings.chats)

    def save_chat_picture(self, chat_id: str) -> str:
        """Store the chat picture and return the URL it is served from, empty when there is none."""
        if not self._telegram_client.is_connected:
            return ""

        chat_id = int(chat_id)

        self._logger.debug("Saving chat picture for chat %s", chat_id)

        try:
            is_group = is_group_or_channel(chat_id)

            output_filename = self._chat_picture_path(chat_id)
            os.makedirs(os.path.dirname(output_filename), exist_ok=True)

            file_id = None
            if is_group:
                json_data = self._telegram_client.send_request("getChat", HttpMethod.GET, params={"chat_id": chat_id})
                file_id = json_data.get("result", {}).get("photo", {}).get("small_file_id")
            else:
                json_data = self._telegram_client.send_request(
                    "getUserProfilePhotos", HttpMethod.GET, params={"limit": 1, "user_id": chat_id}
                )
                photos = json_data.get("result", {}).get("photos", [])
                if photos and photos[0]:
                    file_id = photos[0][0].get("file_id")

            if not file_id:
                self._logger.debug("Chat %s has no photo", chat_id)

                try:
                    os.remove(output_filename)
                except Exception:
                    pass

                return ""

            img_bytes = self._telegram_client.download_file(file_id)
            with Image.open(io.BytesIO(img_bytes)) as img:
                img = img.resize(PICTURE_SIZE, Image.LANCZOS)
                img.save(output_filename, format="JPEG")

            self._logger.info("Saved chat picture for chat id %s", chat_id)

            # Nocache is used to force image refresh in the known chats table
            nocache = int(time.time())

            return f"/plugin/telegram/img/user/pic{chat_id}.jpg?nocache={nocache}"
        except Exception:
            self._logger.exception("Caught an exception saving chat picture for chat_id %s", chat_id)
            return ""

    def _chat_picture_path(self, chat_id) -> str:
        return os.path.join(self._data_folder, "img", "user", f"pic{int(chat_id)}.jpg")
