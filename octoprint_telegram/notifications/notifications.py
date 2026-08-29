from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..emoji import Emoji
from ..telegram import Markup
from . import templating
from .variables import NotificationVariables

if TYPE_CHECKING:
    from octoprint.filemanager import FileManager
    from octoprint.printer import PrinterInterface

    from ..core.settings import Settings
    from ..domain.mute import MutedChats
    from ..integrations.display_layer_progress import DisplayLayerProgress
    from ..integrations.octoprint_api import OctoPrintApi
    from ..integrations.plugins import Plugins
    from ..integrations.thumbnails import Thumbnails
    from ..telegram.client import TelegramClient
    from ..telegram.sender import Sender

render_emojis = Emoji.render_emojis


class Notifications:
    """The notifications the bot sends when something happens."""

    def __init__(
        self,
        settings: Settings,
        sender: Sender,
        telegram_client: TelegramClient,
        muted_chats: MutedChats,
        printer: PrinterInterface,
        file_manager: FileManager,
        plugins: Plugins,
        api: OctoPrintApi,
        display_layer_progress: DisplayLayerProgress,
        thumbnails: Thumbnails,
        plugin_name: str,
        logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._sender = sender
        self._telegram_client = telegram_client
        self._muted_chats = muted_chats
        self._printer = printer
        self._file_manager = file_manager
        self._plugins = plugins
        self._api = api
        self._display_layer_progress = display_layer_progress
        self._thumbnails = thumbnails
        self._plugin_name = plugin_name
        self._logger = logger.getChild("Notifications")

        self._current_z = 0.0
        self._last_z = 0.0
        self._last_notification_time = 0
        self._last_prusammu_state = ""

        self._event_handlers = {
            "Alert": self._notify,
            "Connected": self._notify,
            "Disconnected": self._notify,
            "Error": self._notify,
            "gCode_M600": self._notify,
            "Home": self._notify,
            "MovieDone": self._notify,
            "PausedForUser": self._notify,
            "plugin_octolapse_movie_done": self._notify,
            "PrintDone": self._on_print_done,
            "PrinterShutdown": self._notify,
            "PrinterStart": self._notify,
            "PrintFailed": self._on_print_failed,
            "PrintPaused": self._notify,
            "PrintResumed": self._notify,
            "PrintStarted": self._on_print_started,
            "PrusaMMU_Error": self._on_prusa_mmu,
            "PrusaMMU_Status": self._on_prusa_mmu,
            "StatusNotConnected": self._notify,
            "StatusNotPrinting": self._notify,
            "StatusPrinting": self._notify,
            "UserNotif": self._notify,
            "ZChange": self._on_z_change,
        }

    def send_notification(self, event: str, payload: dict | None = None, chat_id: str | None = None) -> None:
        """Send the notification configured for an event to the chats subscribed to it."""
        handler = self._event_handlers.get(event)
        if handler is None:
            return

        if not self._telegram_client.is_connected:
            self._logger.warning("Received an event, but bot is not ready")
            return

        self._logger.debug("Received a known event: %s - Payload: %s", event, payload)

        # Not all events have payload
        payload = payload or {}

        status = self._printer.get_current_data()
        self._current_z = status["currentZ"] or 0.0
        handler(payload, event, chat_id)

    def is_notification_necessary(self, new_z: float | None = None, old_z: float | None = None) -> bool:
        """
        Whether a notification has to be sent on the gcode ZChange event.

        Depends on notification time and notification height.
        """
        timediff = self._settings.notification_time
        # Check the timediff
        if timediff and timediff > 0 and self._last_notification_time + timediff * 60 <= time.time():
            self._last_notification_time = time.time()
            return True
        zdiff = self._settings.notification_height
        if zdiff and zdiff > 0.0:
            if old_z is None or new_z is None or new_z < 0:
                return False
            # Check the zdiff - ignore big height changes
            if abs(new_z - (old_z or 0.0)) >= 1.0:
                self._last_z = new_z
                return False
            if new_z >= self._last_z + zdiff or new_z < self._last_z:
                self._last_z = new_z
                return True
        return False

    ##########
    ### Event handlers
    ##########

    def _on_z_change(self, payload: dict, event: str, chat_id: str | None) -> None:
        status = self._printer.get_current_data()
        if not status["state"]["flags"]["printing"] or not self.is_notification_necessary(
            payload["new"], payload["old"]
        ):
            return
        self._current_z = payload["new"]
        self._logger.debug(
            "Z-Change. new_z=%.2f old_z=%.2f last_z=%.2f notification_height=%.2f notification_time=%d",
            self._current_z,
            payload["old"],
            self._last_z,
            self._settings.notification_height,
            self._settings.notification_time,
        )
        self._notify(payload, event, chat_id)

    def _on_print_started(self, payload: dict, event: str, chat_id: str | None) -> None:
        self._last_z = 0.0
        self._last_notification_time = time.time()
        self._notify(payload, event, chat_id)

    def _on_print_done(self, payload: dict, event: str, chat_id: str | None) -> None:
        self._muted_chats.unmute_all()
        self._notify(payload, event, chat_id, delay=self._settings.message_at_print_done_delay)

    def _on_print_failed(self, payload: dict, event: str, chat_id: str | None) -> None:
        self._muted_chats.unmute_all()
        self._notify(payload, event, chat_id)

    def _on_prusa_mmu(self, payload: dict, event: str, chat_id: str | None) -> None:
        state = payload.get("state", "")
        if state != self._last_prusammu_state:
            self._last_prusammu_state = state
            self._notify(payload, event, chat_id)

    ##########
    ### Rendering and sending
    ##########

    def _notify(self, payload: dict, event: str, chat_id: str | None = None, delay: int = 0) -> None:
        try:
            variables = NotificationVariables(
                event=event,
                payload=payload,
                current_z=self._current_z,
                printer=self._printer,
                file_manager=self._file_manager,
                plugins=self._plugins,
                api=self._api,
                display_layer_progress=self._display_layer_progress,
                settings=self._settings,
            )

            event = variables.event

            thumbnail = None
            try:
                if event == "PrintStarted":
                    storage_name = payload.get("origin")
                    file_path = payload.get("path")
                    if storage_name and file_path:
                        thumbnail = self._thumbnails.get_thumbnail(storage_name, file_path)
            except Exception:
                self._logger.exception("Exception on getting thumbnail")

            movie = payload.get("movie")

            message_settings = self._settings.message(event)

            markup_setting = message_settings.get("markup") or Markup.OFF.value
            try:
                markup = Markup(markup_setting)
            except ValueError:
                self._logger.warning("Unknown markup '%s' configured for the event %s", markup_setting, event)
                markup = Markup.OFF

            silent = bool(message_settings.get("silent") or False)
            with_image = bool(message_settings.get("image") or False)
            with_gif = self._settings.send_gif and bool(message_settings.get("gif") or False)

            # Log locals for debugging (only accessed variables to avoid triggering lazy calculation)
            debug_info = {
                "event": event,
                "payload": payload,
                "chat_id": chat_id,
                "markup": markup.value,
                "delay": delay,
                "silent": silent,
                "with_image": with_image,
                "with_gif": with_gif,
                "thumbnail_bytes": len(thumbnail) if thumbnail else 0,
                "movie": movie,
                "accessed_variables": variables.accessed_names(),
            }
            self._logger.debug("Notification debug info: %s", debug_info)

            # Format the message
            try:
                message_template = message_settings["text"]

                # Render emojis
                message = render_emojis(message_template)

                # Render template variables
                message = templating.render(message, variables, markup, self._logger)
            except Exception:
                self._logger.exception("Caught an exception while formatting the message")
                message = render_emojis(
                    f"{{emo:attention}} I was not able to format the Notification for the event '{event}' properly.\n"
                    f"Please open your OctoPrint settings for {self._plugin_name} and check message settings for the event '{event}'."
                )

            # Send the message
            self._logger.debug("Sending notification: %s", message)
            if chat_id:
                self._sender.send_message(
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
            else:
                self._sender.notify(
                    event,
                    message,
                    markup=markup,
                    delay=delay,
                    silent=silent,
                    with_image=with_image,
                    with_gif=with_gif,
                    thumbnail=thumbnail,
                    movie=movie,
                )
        except Exception:
            self._logger.exception("Caught an exception sending a notification")
