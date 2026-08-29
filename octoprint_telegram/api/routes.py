from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from flask import jsonify
from octoprint.access.permissions import Permissions

from ..commands import registry
from ..notifications import NOTIFICATION_DEFINITIONS

if TYPE_CHECKING:
    from flask import Response
    from werkzeug.datastructures import MultiDict

    from ..core.context import PluginContext

SUGGESTED_PLUGIN_IDS = [
    "cancelobject",
    "cost",
    "DisplayLayerProgress",
    "domoticz",
    "enclosure",
    "filamentmanager",
    "gpiocontrol",
    "ikea_tradfri",
    "multicam",
    "mystromswitch",
    "octohue",
    "octolapse",
    "octolight",
    "octolightHA",
    "octorelay",
    "orvibos20",
    "prusammu",
    "prusaslicerthumbnails",
    "psucontrol",
    "resource_monitor",
    "SlicerSettingsParser",
    "Spoolman",
    "SpoolManager",
    "tasmota_mqtt",
    "tasmota",
    "tplinksmartplug",
    "tuyasmartplug",
    "usbrelaycontrol",
    "wemoswitch",
    "wled",
    "ws281x_led_status",
    "wyze",
]


class Api:
    """The plugin's own HTTP API, used by its settings page."""

    def __init__(self, plugin_context: PluginContext) -> None:
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("Api")

    def handle_get(self, request_args: MultiDict | None = None) -> Response:
        # /?enrollmentCountdown
        if request_args and "enrollmentCountdown" in request_args:
            return jsonify({"remaining": self.plugin_context.enrollment.remaining_seconds})

        # /?bindings
        if request_args and "bindings" in request_args:
            bind_text = {}
            for name, definition in NOTIFICATION_DEFINITIONS.items():
                if definition.bind_message:
                    bind_text.setdefault(definition.bind_message, []).append({name: definition.description})
            return jsonify(
                {
                    "bind_cmd": {command.name: command.description for command in registry.configurable_per_chat()},
                    "bind_msg": {
                        name: definition.description
                        for name, definition in NOTIFICATION_DEFINITIONS.items()
                        if not definition.bind_message
                    },
                    "bind_text": bind_text,
                    "no_setting": [
                        name
                        for name, definition in NOTIFICATION_DEFINITIONS.items()
                        if not definition.shown_in_settings
                    ],
                }
            )

        # /?default_messages
        if request_args and "default_messages" in request_args:
            return jsonify({name: definition.as_settings() for name, definition in NOTIFICATION_DEFINITIONS.items()})

        # /?requirements
        if request_args and "requirements" in request_args:
            settings_ffmpeg = self.plugin_context.octoprint_settings.ffmpeg_path
            ffmpeg_path = (
                settings_ffmpeg
                if isinstance(settings_ffmpeg, str)
                and os.path.isfile(settings_ffmpeg)
                and os.access(settings_ffmpeg, os.X_OK)
                else shutil.which("ffmpeg")
            )

            cpulimiter_path = shutil.which("cpulimit") or shutil.which("limitcpu")

            return jsonify(
                {
                    "ffmpeg_path": ffmpeg_path,
                    "cpulimiter_path": cpulimiter_path,
                    **{
                        plugin_id: self.plugin_context.plugins.status(plugin_id).value
                        for plugin_id in SUGGESTED_PLUGIN_IDS
                    },
                }
            )

        # /
        ret_chats = self.plugin_context.chats.all_chats

        return jsonify(
            {
                "chats": ret_chats,
                "connection_state_str": self.plugin_context.connection_status.message,
                "connection_ok": self.plugin_context.connection_status.ok,
            }
        )

    def get_api_commands(self) -> dict[str, list[str]]:
        return {
            "delChat": ["chat_id"],
            "editChat": [
                "chat_id",
                "accept_commands",
                "send_notifications",
                "allow_users",
            ],
            "startEnrollmentCountdown": [],
            "stopEnrollmentCountdown": [],
            "testToken": ["token"],
        }

    def handle_command(self, command: str, data: dict) -> Response | tuple[Response, int] | None:
        self._logger.info("Received API command %s with data %s", command, data)

        if not Permissions.SETTINGS.can():
            self._logger.warning("API command was not allowed")
            return jsonify({"ok": False, "error": "Insufficient permissions"}), 403

        if command == "testToken":
            token_to_test = str(data.get("token")).strip()

            if not token_to_test:
                return jsonify(
                    {
                        "ok": False,
                        "connection_state_str": "Token is empty",
                        "username": None,
                    }
                )

            try:
                # This will raise an exception if token is invalid
                username = self.plugin_context.telegram_client.get_bot_username(token_to_test)

                return jsonify(
                    {
                        "ok": True,
                        "connection_state_str": f"Token valid for {username}",
                        "username": username,
                    }
                )
            except Exception as e:
                self._logger.exception("Caught an exception testing token")
                return jsonify(
                    {
                        "ok": False,
                        "connection_state_str": f"Error testing token: {e}",
                        "username": None,
                    }
                )

        elif command == "delChat":
            chat_id = str(data.get("chat_id"))

            is_chat_unknown = self.plugin_context.chats.get_chat(chat_id) is None
            if is_chat_unknown:
                self._logger.warning("Chat id %s is unknown", chat_id)
                return jsonify({"ok": False, "error": "Unknown chat with given id"}), 404

            try:
                self.plugin_context.chats.remove_chat(chat_id)
                self._logger.info("Chat %s has been deleted via API", chat_id)
            except Exception:
                self._logger.exception("Caught an exception in delChat API command")
                return jsonify({"ok": False, "error": "Cannot delete chat, please check logs"}), 500

            # Return updated chats settings
            return self.handle_get()

        elif command == "editChat":
            chat_id = str(data.get("chat_id"))
            settings_chat = self.plugin_context.chats.get_chat(chat_id)

            # Check if chat is unknown
            if not settings_chat:
                self._logger.warning("Chat id %s is unknown", chat_id)
                return jsonify({"ok": False, "error": "Unknown chat with given id"}), 404

            settings_keys = ("accept_commands", "send_notifications", "allow_users")

            # Check that settings_keys are boolean
            invalid_keys = [k for k in settings_keys if not isinstance(data.get(k), bool)]
            if invalid_keys:
                self._logger.warning("Received args %s are not boolean", ", ".join(invalid_keys))
                return jsonify(
                    {"ok": False, "error": f"Invalid values: {', '.join(invalid_keys)} must be boolean"}
                ), 400

            # Update user
            for key in settings_keys:
                settings_chat[key] = data[key]
            self.plugin_context.settings.set_chat(chat_id, settings_chat)
            self.plugin_context.settings.save()

            # Logging successful user update
            settings = ", ".join(f"{k}={data[k]}" for k in settings_keys)
            self._logger.info("Updated settings for chat %s: %s", chat_id, settings)

            # Return updated chats settings
            return self.handle_get()

        elif command == "startEnrollmentCountdown":
            duration = self.plugin_context.enrollment.open()
            self.plugin_context.frontend.update_enrollment_countdown(duration)
            return jsonify({"ok": True, "duration": duration})

        elif command == "stopEnrollmentCountdown":
            self.plugin_context.enrollment.close()
            self.plugin_context.frontend.update_enrollment_countdown(0)
            return jsonify({"ok": True})
