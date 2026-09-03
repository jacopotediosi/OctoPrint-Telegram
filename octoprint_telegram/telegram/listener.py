from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

from typing_extensions import override

from ..utils import format_short_exception
from .dispatcher import SUPPORTED_UPDATE_TYPES
from .enums import HttpMethod

if TYPE_CHECKING:
    from ..core.context import PluginContext
    from .dispatcher import Dispatcher

# How long to wait before retrying after a failed call to Telegram
RETRY_DELAY_SECONDS = 120

# How long Telegram holds a long-polling request open
LONG_POLL_SECONDS = 30


class Listener(threading.Thread):
    """Fetches updates from Telegram and hands each one to the dispatcher."""

    def __init__(self, plugin_context: PluginContext, dispatcher: Dispatcher) -> None:
        """Set up the fetching of the updates from Telegram.

        Args:
            plugin_context (PluginContext): The plugin context.
            dispatcher (Dispatcher): The dispatcher of received updates.
        """
        threading.Thread.__init__(self, daemon=True)
        self.plugin_context = plugin_context
        self._dispatcher = dispatcher
        self._telegram_client = plugin_context.telegram_client
        self._logger = plugin_context.logger.getChild("Listener")
        self._update_offset = 0
        self._first_contact = True
        self._do_stop = False
        self._username = "UNKNOWN"

    @override
    def run(self) -> None:
        self._logger.debug("Try first connect.")
        self._try_first_contact()

        self._logger.debug("Listener is running.")

        # Repeat fetching and processing messages until thread stopped
        while not self._do_stop:
            try:
                self._process_updates()
            except Exception:
                self._logger.exception("Caught an exception calling _process_updates()")

        self._logger.debug("Listener exits NOW.")

    def _try_first_contact(self) -> None:
        got_contact = False
        while not self._do_stop and not got_contact:
            try:
                token = self.plugin_context.settings.token
                self._username = self._telegram_client.get_bot_username(token)
                got_contact = True
                self._set_status(f"Connected as {self._username}", ok=True)
            except Exception as e:
                error_message = (
                    f"Caught an exception connecting to telegram: {format_short_exception(e)}. "
                    "Waiting 2 minutes before trying again."
                )

                self._logger.exception(error_message)
                self._set_status(error_message)

                time.sleep(RETRY_DELAY_SECONDS)

    def _process_updates(self) -> None:
        # Try to check for incoming messages. Wait 120 seconds and repeat on failure.
        try:
            updates = self._get_updates()
        except Exception as e:
            error_message = (
                f"Caught an exception getting updates: {format_short_exception(e)}. "
                "Waiting 2 minutes before trying again."
            )

            self._logger.exception(error_message)
            self._set_status(error_message)

            time.sleep(RETRY_DELAY_SECONDS)
            return

        for update in updates:
            try:
                self._dispatcher.process_update(update)
            except Exception:
                self._logger.exception("Caught an exception processing a message")

        try:
            if (
                self.plugin_context.settings.force_loop_message
                and self.plugin_context.printer.is_printing()
                and self.plugin_context.notifications.is_notification_necessary()
            ):
                self._logger.debug("ForceLoopMessage on_event StatusPrinting")
                self.plugin_context.notifications.send_notification("StatusPrinting")
        except Exception:
            self._logger.exception("Exception ForceLoopMessage caught!")

        self._set_status(f"Connected as {self._username}", ok=True)
        # We had first contact after octoprint startup so lets send startup message
        if self._first_contact:
            self._first_contact = False
            self.plugin_context.notifications.send_notification("PrinterStart")

    def _set_update_offset(self, new_value: int) -> None:
        """Move the update offset forward, never backwards.

        Args:
            new_value (int): The id of the last update handled.
        """
        if new_value >= self._update_offset:
            self._logger.debug("Updating update_offset from %s to %s", self._update_offset, 1 + new_value)
            self._update_offset = 1 + new_value
        else:
            self._logger.debug(
                "Not changing update_offset - otherwise would reduce it from %s to %s",
                self._update_offset,
                1 + new_value,
            )

    def _get_updates(self) -> list[dict]:
        # If it is the first contact, drain the updates backlog
        if self._update_offset == 0 and self._first_contact:
            json_data = self._telegram_client.send_request(
                "getUpdates",
                HttpMethod.GET,
                params={"offset": -1, "timeout": 0},
            )

            results = json_data["result"]
            if results:
                self._set_update_offset(results[-1]["update_id"])

            self._logger.debug("Ignored all messages until now because first_contact was True.")

            return []

        # Else, get the updates
        json_data = self._telegram_client.send_request(
            "getUpdates",
            HttpMethod.GET,
            params={
                "offset": self._update_offset,
                "timeout": LONG_POLL_SECONDS,
                "allowed_updates": json.dumps(SUPPORTED_UPDATE_TYPES),
            },
        )

        # Update update_offset
        results = json_data["result"]
        for entry in results:
            self._set_update_offset(entry["update_id"])

        # Return results
        return results

    def stop(self) -> None:
        """Ask the listener to stop."""
        self._do_stop = True

    def _set_status(self, status: str, ok: bool = False) -> None:
        if self.plugin_context.connection_status.message == status:
            return

        if self._do_stop:
            self._logger.debug("Would set status but do_stop is True: %s", status)
            return

        self._logger.debug("Setting status: %s", status)
        self.plugin_context.connection_status.set(status, ok)
