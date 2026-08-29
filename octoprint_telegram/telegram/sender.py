from __future__ import annotations

import html
import json
import logging
import os
import time
from typing import TYPE_CHECKING

from ..emoji import Emoji
from .chat_action import chat_action
from .enums import ChatAction, HttpMethod, Markup
from .keyboards import Buttons

if TYPE_CHECKING:
    from ..core.connection_status import ConnectionStatus
    from ..domain.chats import Chats
    from ..domain.mute import MutedChats
    from ..media import Media
    from .client import TelegramClient

render_emojis = Emoji.render_emojis

# Telegram refuses uploads above this size
MAX_UPLOAD_MEGABYTES = 50

ERROR_MESSAGE = "I tried to send you a message, but an exception occurred. Please check the logs."


class Sender:
    """Delivers messages and files to Telegram chats."""

    def __init__(
        self,
        telegram_client: TelegramClient,
        chats: Chats,
        muted_chats: MutedChats,
        media: Media,
        connection_status: ConnectionStatus,
        logger: logging.Logger,
    ) -> None:
        """Set up the delivery of messages and files.

        Args:
            telegram_client (TelegramClient): The Telegram Bot API.
            chats (Chats): The chats the bot knows about.
            muted_chats (MutedChats): The chats that asked to receive no notifications.
            media (Media): The pictures and videos taken from the webcams.
            connection_status (ConnectionStatus): The connection status.
            logger (logging.Logger): The logger to write to.
        """
        self._telegram_client = telegram_client
        self._chats = chats
        self._muted_chats = muted_chats
        self._media = media
        self._connection_status = connection_status
        self._logger = logger.getChild("Sender")

    ##########
    ### Messages
    ##########

    def send_message(
        self,
        message: str,
        chat_id: str,
        *,
        message_id: str = "",
        markup: Markup = Markup.OFF,
        buttons: Buttons | None = None,
        delay: int = 0,
        silent: bool = False,
        with_image: bool = False,
        with_gif: bool = False,
        gif_duration: int = 5,
        thumbnail: bytes | None = None,
        movie: str | None = None,
    ) -> str | None:
        """Send a message to a chat, or replace an earlier one when its id is given.

        Replacing a message only honours markup, buttons and delay; the attachments and the silent flag are ignored.

        Args:
            message (str): The text to send.
            chat_id (str): The chat to send it to.
            message_id (str, optional): The message to replace instead of sending a new one.
            markup (Markup, optional): The markup Telegram parses in the text.
            buttons (Buttons, optional): The inline keyboard shown under the message.
            delay (int, optional): Seconds to wait before delivering.
            silent (bool, optional): Deliver without a notification sound.
            with_image (bool, optional): Attach a snapshot from every configured webcam.
            with_gif (bool, optional): Attach a video from every configured webcam.
            gif_duration (int, optional): Seconds of video to record from each webcam.
            thumbnail (bytes, optional): Content of a thumbnail image to attach.
            movie (str, optional): Path on disk of a video to attach.

        Returns:
            str | None: The id of the message, or None if it could not be delivered.
        """
        if not self._telegram_client.is_connected:
            return None

        try:
            # Delay
            if delay > 0:
                self._logger.debug("Sleeping %s seconds", delay)
                time.sleep(delay)

            # Prepare message data
            message_data = {"chat_id": chat_id}
            self._apply_markup(message_data, markup)
            self._apply_buttons(message_data, buttons)

            if message_id:
                self._edit(message, chat_id, message_data=message_data, message_id=message_id)
                return message_id

            return self._send(
                message,
                chat_id,
                message_data=message_data,
                with_image=with_image,
                with_gif=with_gif,
                silent=silent,
                gif_duration=gif_duration,
                thumbnail=thumbnail,
                movie=movie,
            )
        except Exception:
            self._logger.exception("Caught an exception in send_message()")
            return None

    def notify(
        self,
        event: str,
        message: str,
        *,
        markup: Markup = Markup.OFF,
        delay: int = 0,
        silent: bool = False,
        with_image: bool = False,
        with_gif: bool = False,
        thumbnail: bytes | None = None,
        movie: str | None = None,
    ) -> None:
        """Send a message to every chat subscribed to an event."""
        if not self._telegram_client.is_connected:
            return

        self._logger.debug("notify() - event: %s", event)

        for chat_id in self._chats.get_chats_subscribed_to(event):
            try:
                if not self._muted_chats.is_muted(chat_id):
                    self.send_message(
                        message,
                        chat_id,
                        markup=markup,
                        delay=delay,
                        silent=silent,
                        with_image=with_image,
                        with_gif=with_gif,
                        thumbnail=thumbnail,
                        movie=movie,
                    )
            except Exception:
                self._logger.exception("Caught an exception processing chat %s", chat_id)

    def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete a message previously sent to a chat."""
        self._telegram_client.send_request(
            "deleteMessage",
            HttpMethod.POST,
            data={"chat_id": chat_id, "message_id": message_id},
        )

    ##########
    ### Files
    ##########

    def send_file(self, chat_id: str, path: str, caption: str = "") -> None:
        """Send a file from disk to a chat."""
        if not self._telegram_client.is_connected:
            return

        self._logger.info("Sending file %s to chat %s", path, chat_id)

        if not self._fits_upload_limit(os.path.getsize(path), f"the file '{path}'"):
            self.send_message(
                render_emojis(
                    f"{{emo:warning}} The file <code>{html.escape(os.path.basename(path))}</code> is too large "
                    f"(>{MAX_UPLOAD_MEGABYTES}MB) to send via Telegram. "
                    "Please download it manually from the OctoPrint web interface."
                ),
                chat_id,
                markup=Markup.HTML,
            )
            return

        with chat_action(self._telegram_client, chat_id, ChatAction.UPLOAD_DOCUMENT, self._logger), open(
            path, "rb"
        ) as document:
            self._telegram_client.send_request(
                "sendDocument",
                HttpMethod.POST,
                files={"document": document},
                data={"chat_id": chat_id, "caption": caption},
            )

    ##########
    ### Delivery
    ##########

    def _edit(
        self,
        message: str,
        chat_id: str,
        *,
        message_data: dict,
        message_id: str,
    ) -> None:
        """Replace the text of a message previously sent, identified by its id."""
        try:
            message_data["text"] = message
            message_data["message_id"] = message_id

            self._logger.debug("Sending a message update in chat %s: %s", chat_id, message_data)

            self._telegram_client.send_request("editMessageText", HttpMethod.POST, data=message_data)
        except Exception as e:
            if "Bad Request: message is not modified" not in getattr(e, "telegram_response_text", ""):
                self._logger.exception("Caught an exception in _edit()")
                self._report_failure(chat_id)

    def _send(
        self,
        message: str,
        chat_id: str,
        *,
        message_data: dict,
        with_image: bool = False,
        with_gif: bool = False,
        silent: bool = False,
        gif_duration: int = 5,
        thumbnail: bytes | None = None,
        movie: str | None = None,
    ) -> str | None:
        """Deliver a new message to a chat."""
        try:
            message_data["link_preview_options"] = json.dumps({"is_disabled": True})
            message_data["disable_notification"] = silent

            # Prepare images and gifs to send
            images_to_send = []
            gifs_to_send = []

            # Add thumbnail to images to send
            if thumbnail:
                images_to_send.append(thumbnail)

            # Add movie to gifs to send
            if movie:
                if self._fits_upload_limit(os.path.getsize(movie), "the movie"):
                    gifs_to_send.append(movie)
                else:
                    message += (
                        "\nThe timelapse/Octolapse video could not be sent via Telegram because its size exceeds "
                        f"{MAX_UPLOAD_MEGABYTES}MB. Please download it manually from the OctoPrint web interface."
                    )

            if with_image or with_gif:
                with chat_action(self._telegram_client, chat_id, ChatAction.RECORD_VIDEO, self._logger):
                    # Pre image
                    try:
                        self._media.hooks.run_before_image()
                    except Exception:
                        self._logger.exception("Caught an exception calling run_before_image()")

                    # Add webcam images to images to send
                    if with_image:
                        try:
                            images_to_send += self._media.snapshots.take_all_images()
                        except Exception:
                            self._logger.exception("Caught an exception taking all images")

                    # Add webcam gifs to gifs to send
                    if with_gif:
                        try:
                            gifs_to_send += self._media.video.take_all_gifs(gif_duration)
                        except Exception:
                            self._logger.exception("Caught an exception taking all gifs")

                    # Post image
                    try:
                        self._media.hooks.run_after_image()
                    except Exception:
                        self._logger.exception("Caught an exception calling run_after_image()")

            # Initialize files and media
            files = {}
            media = []

            # Add images to send to files and media
            for i, image_to_send in enumerate(images_to_send):
                if not self._fits_upload_limit(len(image_to_send), "an image"):
                    continue

                files[f"photo_{i}"] = image_to_send
                media.append({"type": "photo", "media": f"attach://photo_{i}"})

            # Add gifs to send to files and media
            for i, gif_to_send in enumerate(gifs_to_send):
                try:
                    if not self._fits_upload_limit(os.path.getsize(gif_to_send), "a gif"):
                        continue

                    with open(gif_to_send, "rb") as gif_file:
                        files[f"video_{i}"] = gif_file.read()

                    media.append({"type": "video", "media": f"attach://video_{i}"})
                except Exception:
                    self._logger.exception("Caught an exception reading gif file")

            # Add the message as the caption of the first media
            if media and message:
                media[0]["caption"] = message
                if message_data.get("parse_mode"):
                    media[0]["parse_mode"] = message_data["parse_mode"]

            # If there are media, send a media-group message
            if media:
                self._logger.debug("Sending message with media, chat id: %s", chat_id)

                action = ChatAction.UPLOAD_VIDEO if gifs_to_send else ChatAction.UPLOAD_PHOTO
                with chat_action(self._telegram_client, chat_id, action, self._logger):
                    message_data["media"] = json.dumps(media)
                    response = self._telegram_client.send_request(
                        "sendMediaGroup", HttpMethod.POST, data=message_data, files=files
                    )
                return str(response["result"][0]["message_id"])
            # If there aren't media, send a text-only message
            else:
                self._logger.debug("Sending text-only message, chat id: %s", chat_id)

                with chat_action(self._telegram_client, chat_id, ChatAction.TYPING, self._logger):
                    message_data["text"] = message
                    response = self._telegram_client.send_request("sendMessage", HttpMethod.POST, data=message_data)
                return str(response["result"]["message_id"])
        except Exception:
            self._logger.exception("Caught an exception in _send()")
            self._report_failure(chat_id)
            return None

    def _fits_upload_limit(self, size_in_bytes: int, description: str) -> bool:
        """Whether something of a given size is small enough to upload.

        Args:
            size_in_bytes (int): The size of what has to be uploaded.
            description (str): The name the log warning gives it.

        Returns:
            bool: True if the size is within the limit.
        """
        if size_in_bytes <= MAX_UPLOAD_MEGABYTES * 1024 * 1024:
            return True

        self._logger.warning("Skipping %s because it exceeds the %sMB upload limit", description, MAX_UPLOAD_MEGABYTES)
        return False

    def _apply_markup(self, data: dict, markup: Markup) -> None:
        if markup is not Markup.OFF:
            data["parse_mode"] = markup.value

    def _apply_buttons(self, data: dict, buttons: Buttons | None) -> None:
        if not buttons:
            return
        rows = [[{"text": button[0], "callback_data": button[1]} for button in row] for row in buttons]
        data["reply_markup"] = json.dumps({"inline_keyboard": rows})

    def _report_failure(self, chat_id: str) -> None:
        self._connection_status.set("Exception sending a message")
        self._telegram_client.send_request(
            "sendMessage",
            HttpMethod.POST,
            data={"chat_id": chat_id, "text": ERROR_MESSAGE},
        )
