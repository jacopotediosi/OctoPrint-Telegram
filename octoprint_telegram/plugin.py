from __future__ import annotations

import logging
import os
import sys
import threading

import octoprint.plugin
import urllib3
from octoprint.access.permissions import Permissions
from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
from octoprint.server import app

from .api import Api
from .commands import registry
from .commands.commands import Commands
from .core import OctoPrintSettings, PluginContext, Settings
from .core.connection_status import ConnectionStatus
from .core.frontend import Frontend
from .core.logging import RedactingFormatter
from .core.migrations import migrate_settings
from .domain.chats import Chats
from .domain.enrollment import Enrollment
from .domain.mute import MutedChats
from .emoji import Emoji
from .integrations import Cost, DisplayLayerProgress, OctoPrintApi, Plugins
from .media import FfmpegPreset, ImageHookMethod, Media
from .notifications import NOTIFICATION_DEFINITIONS, Notifications
from .telegram import ChatAction, ChatType, HttpMethod, Sender
from .telegram.client import TOKEN_REGEX, TelegramClient
from .telegram.dispatcher import Dispatcher
from .telegram.listener import Listener

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TelegramPlugin(
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.WizardPlugin,
):
    # Runs at plugin discovery, before OctoPrint injects its properties
    def __init__(self):
        super().__init__()

        self._logger = logging.getLogger("octoprint.plugins.telegram")

        # State owned by the plugin
        self._connection_status = ConnectionStatus()
        self._listener = None
        self._user_pause_already_notified = False

        # Built by on_startup()
        self._port = None
        self._plugin_context = None
        self._commands = None
        self._api = None
        self._telegram_client = None

    # Runs once OctoPrint has injected its properties, before the settings migration
    def initialize(self):
        # Logging formatter that sanitizes logs by redacting sensitive data (e.g., bot tokens)
        logging_formatter = RedactingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # File logging handler
        file_handler = CleaningTimedRotatingFileHandler(
            self._settings.get_plugin_logfile_path(),
            when="D",
            backupCount=3,
        )
        file_handler.setFormatter(logging_formatter)
        self._logger.addHandler(file_handler)

        # Console logging handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging_formatter)
        self._logger.addHandler(console_handler)

        # Don't propagate logging
        self._logger.propagate = False

        # Emojis
        Emoji.init(self._settings)
        app.jinja_env.filters["telegram_emoji"] = Emoji.get_emoji

    ##########
    ### Bot lifecycle
    ##########

    def start_bot(self):
        """Start the telegram bot."""
        token = self._settings.get(["token"])

        if token and self._listener is None:
            self._logger.debug("Starting bot.")

            self._telegram_client.connect(token)

            dispatcher = Dispatcher(self._plugin_context, self._commands)
            self._listener = Listener(self._plugin_context, dispatcher)
            self._listener.start()

            # Set bot commands
            try:
                self._telegram_client.set_bot_commands(
                    [
                        {"command": command.name.lstrip("/"), "description": command.description}
                        for command in registry.shown_to_users()
                    ]
                )
            except Exception:
                self._logger.exception("Caught an exception setting bot commands")

            # Update chats
            try:

                def _update_chats():
                    chats = self._plugin_context.chats
                    for chat_id, chat_settings in chats.all_chats.items():
                        # Delete unreachable chats
                        if chat_settings.get("type") == ChatType.PRIVATE.value:
                            endpoint = "sendChatAction"
                            params = {"chat_id": chat_id, "action": ChatAction.TYPING.value}
                        else:
                            endpoint = "getChat"
                            params = {"chat_id": chat_id}
                        try:
                            self._telegram_client.send_request(endpoint, HttpMethod.GET, params=params, timeout=5)
                        except Exception as e:
                            if '"error_code":403' in getattr(e, "telegram_response_text", ""):
                                self._logger.info("Chat %s is unreachable, removing it from settings...", chat_id)
                                chats.remove_chat(chat_id)
                                continue

                        # Update chat pictures
                        public_path = chats.save_chat_picture(chat_id)
                        self._settings.set(["chats", chat_id, "image"], public_path)

                    # Save settings and update known chats table
                    self._settings.save()
                    self._plugin_context.frontend.update_known_chats(self._settings.get(["chats"]))

                threading.Thread(target=_update_chats, daemon=True).start()
            except Exception:
                self._logger.exception("Caught an exception updating chats")

    def stop_bot(self):
        """Stop the telegram bot."""
        if self._listener is not None:
            self._logger.debug("Stopping bot.")

            self._telegram_client.disconnect()

            self._listener.stop()
            self._listener = None

    ##########
    ### StartupPlugin mixin
    ##########

    # Runs when the server is bound to its host and port, before it starts serving
    def on_startup(self, host, port):
        self._port = port

        self._plugin_context = self._build_plugin_context()
        self._commands = Commands(self._plugin_context)
        self._api = Api(self._plugin_context)

    # Runs once the server is serving and the other plugins are ready
    def on_after_startup(self):
        self.start_bot()

    ##########
    ### Plugin context
    ##########

    def _build_plugin_context(self) -> PluginContext:
        settings = Settings(self._settings)
        octoprint_settings = OctoPrintSettings(self._settings)
        api = OctoPrintApi(
            self._port,
            lambda: getattr(self, "plugin_apikey", None),
            octoprint_settings,
            self._logger,
        )
        plugins = Plugins(self._plugin_manager)
        frontend = Frontend(self._plugin_manager, self._identifier)
        muted_chats = MutedChats()
        enrollment = Enrollment()
        display_layer_progress = DisplayLayerProgress(plugins, api, self._logger)

        self._telegram_client = TelegramClient(settings, self._logger)

        media = Media(
            settings,
            octoprint_settings,
            plugins,
            self._plugin_manager,
            self._printer,
            self._event_bus,
            self.get_plugin_data_folder(),
            self._logger,
        )
        media.clear_temporary_files()

        chats = Chats(
            settings,
            self._telegram_client,
            frontend,
            self.get_plugin_data_folder(),
            lambda: self._new_chat_settings,
            self._logger,
        )
        sender = Sender(
            self._telegram_client,
            chats,
            muted_chats,
            media,
            api,
            self._connection_status,
            self._logger,
        )
        notifications = Notifications(
            settings,
            sender,
            self._telegram_client,
            muted_chats,
            self._printer,
            self._file_manager,
            plugins,
            api,
            display_layer_progress,
            self._plugin_name,
            self._logger,
        )

        return PluginContext(
            logger=self._logger,
            server_port=self._port,
            commands=registry.COMMAND_DEFINITIONS,
            settings=settings,
            octoprint_settings=octoprint_settings,
            telegram_client=self._telegram_client,
            sender=sender,
            connection_status=self._connection_status,
            frontend=frontend,
            chats=chats,
            muted_chats=muted_chats,
            notifications=notifications,
            enrollment=enrollment,
            printer=self._printer,
            printer_profiles=self._printer_profile_manager,
            file_manager=self._file_manager,
            slicing_manager=self._slicing_manager,
            api=api,
            plugins=plugins,
            cost=Cost(self._settings),
        )

    ##########
    ### ShutdownPlugin mixin
    ##########

    def on_shutdown(self):
        self.on_event("PrinterShutdown", {})
        self.stop_bot()

    ##########
    ### SettingsPlugin mixin
    ##########

    def get_settings_defaults(self):
        return {
            "token": "",
            "notification_height": 5.0,
            "notification_time": 15,
            "message_at_print_done_delay": 0,
            "messages": {name: definition.as_settings() for name, definition in NOTIFICATION_DEFINITIONS.items()},
            "chats": {
                "zBOTTOMOFCHATS": {}
            },  # zBOTTOMOFCHATS is a dummy element to avoid bug https://github.com/OctoPrint/OctoPrint/issues/5177
            "send_icon": True,
            "send_gif": False,
            "no_mistake": False,
            "ForceLoopMessage": False,
            "select_file_after_upload": False,
            "sort_files_by_date": False,
            "show_models_in_files": True,
            "no_cpulimit": False,
            "ffmpeg_preset": FfmpegPreset.MEDIUM.value,
            "imgbbApiKey": "",
            "PreImgMethod": ImageHookMethod.NONE.value,
            "PreImgCommand": "",
            "PreImgDelay": 0,
            "PostImgMethod": ImageHookMethod.NONE.value,
            "PostImgCommand": "",
            "PostImgDelay": 0,
            "TimeFormat": "%H:%M:%S",
            "DayTimeFormat": "%a %H:%M:%S",
            "WeekTimeFormat": "%d.%m.%Y %H:%M:%S",
            "http_proxy": "",
            "https_proxy": "",
        }

    @property
    def _new_chat_settings(self):
        """The settings a chat starts with."""
        return {
            "title": "[UNKNOWN]",
            "accept_commands": False,
            "send_notifications": False,
            "type": ChatType.PRIVATE.value,
            "image": "",
            "allow_users": False,
            "commands": {command.name: False for command in registry.configurable_per_chat()},
            "notifications": {notification: False for notification in NOTIFICATION_DEFINITIONS},
        }

    def get_settings_preprocessors(self):
        return (
            {},
            {
                "notification_height": lambda x: float(x),
                "notification_time": lambda x: int(x),
            },
        )

    def get_settings_version(self):
        # Settings version numbers used in releases
        # < 1.3.0: no settings versioning
        # 1.3.0:  1
        # 1.3.1:  2
        # 1.4.0:  3
        # 1.4.3:  4
        # 1.5.1:  5
        # 1.9.0:  6
        # 1.10.0: 7
        return 7

    def on_settings_migrate(self, target, current=None):
        migrate_settings(
            target,
            current,
            self._settings,
            lambda: self._new_chat_settings,
            self._logger,
        )

    def on_settings_save(self, data):
        self._logger.debug("Saving settings: %s", data)

        # Get old token from settings
        old_token = self._settings.get(["token"])

        # If there is a new token in data
        if "token" in data:
            # Strip the token
            data["token"] = data["token"].strip()

            # Check token format
            if not TOKEN_REGEX.fullmatch(data["token"]):
                data["token"] = ""
                self._logger.error("Not saving token because it doesn't seem to have the right format.")
                self._connection_status.set(
                    "The previously entered token doesn't seem to have the correct format. "
                    "It should look like this: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11."
                )

        # Now save settings
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

        # Reconnect if the token changed
        if "token" in data and data["token"] != old_token:
            self.stop_bot()
            self.start_bot()

    def get_settings_restricted_paths(self):
        return {"admin": [["token"], ["chats"]]}

    ##########
    ### AssetPlugin mixin
    ##########

    def get_assets(self):
        return {
            "js": ["js/telegram.js"],
            "css": ["css/telegram.css"],
        }

    ##########
    ### TemplatePlugin mixin
    ##########

    def get_template_configs(self):
        return [{"type": "settings", "name": "Telegram", "custom_bindings": True}]

    def get_template_vars(self):
        return {"custom_emoji_map": Emoji.get_custom_emoji_map(), "plugin_version": self._plugin_version}

    def is_template_autoescaped(self):
        return True

    ##########
    ### WizardPlugin mixin
    ##########

    def is_wizard_required(self):
        return self._settings.get(["token"]) == ""

    def get_wizard_version(self):
        return 1
        # Wizard version numbers used in releases
        # < 1.4.2 : no wizard
        # 1.4.2 : 1
        # 1.4.3 : 1

    ##########
    ### SimpleApiPlugin mixin
    ##########

    def is_api_protected(self):
        return True

    def on_api_get(self, request):
        if not Permissions.SETTINGS.can():
            return "Insufficient permissions", 403

        return self._api.handle_get(request.args)

    def get_api_commands(self):
        return self._api.get_api_commands()

    def on_api_command(self, command, data):
        return self._api.handle_command(command, data)

    ##########
    ### EventHandlerPlugin mixin
    ##########

    def on_event(self, event, payload, **kwargs):
        try:
            if not self._plugin_context:
                self._logger.debug("Received an event, but the plugin is not initialized yet")
                return

            if event == "plugin_prusammu_mmu_changed":
                if payload["state"] in ("NOT_FOUND", "PAUSED_USER", "ATTENTION"):
                    event = "PrusaMMU_Error"
                elif payload["state"] in ("UNLOADING", "UNLOADING_FINAL", "LOADING", "LOADED", "CUTTING", "EJECTING"):
                    event = "PrusaMMU_Status"

            self._plugin_context.notifications.send_notification(event, payload)
        except Exception:
            self._logger.exception("Caught an exception handling an event")

    ##########
    ### Hooks
    ##########

    def get_update_information(self, *args, **kwargs):
        return {
            "telegram": {
                "displayName": self._plugin_name,
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "current": self._plugin_version,
                "user": "jacopotediosi",
                "repo": "OctoPrint-Telegram",
                "pip": "https://github.com/jacopotediosi/OctoPrint-Telegram/archive/{target_version}.zip",
            }
        }

    def route_hook(self, server_routes, *args, **kwargs):
        from octoprint.server.util.flask import (
            permission_validator,
        )
        from octoprint.server.util.tornado import (
            LargeResponseHandler,
            access_validation_factory,
        )

        os.makedirs(os.path.join(self.get_plugin_data_folder(), "img", "user"), exist_ok=True)

        return [
            (
                r"/img/user/(.*)",
                LargeResponseHandler,
                {
                    "path": os.path.join(self.get_plugin_data_folder(), "img", "user"),
                    "allow_client_caching": False,
                    "access_validation": access_validation_factory(
                        app,
                        permission_validator,
                        Permissions.SETTINGS,
                    ),
                },
            ),
            (
                r"/static/img/(.*)",
                LargeResponseHandler,
                {
                    "path": os.path.join(self._basefolder, "static", "img"),
                    "allow_client_caching": True,
                    "access_validation": access_validation_factory(
                        app,
                        permission_validator,
                        Permissions.SETTINGS,
                    ),
                },
            ),
        ]

    def hook_gcode_received(self, comm_instance, line, *args, **kwargs):
        try:
            if line.startswith(("echo:busy: paused for user", "// action:paused")):
                if not self._user_pause_already_notified:
                    self.on_event("PausedForUser", {})
                    self._user_pause_already_notified = True
            elif line.startswith("echo:UserNotif"):
                self.on_event("UserNotif", {"UserNotif": line[15:]})
            elif line.startswith("ok"):
                self._user_pause_already_notified = False
        except Exception:
            self._logger.exception("Caught an exception on hook_gcode_received")

        return line

    def hook_gcode_sent(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        try:
            if gcode and gcode == "M600":
                self.on_event("gCode_M600", {})
        except Exception:
            self._logger.exception("Caught an exception on hook_gcode_sent")

    def register_custom_events(self, *args, **kwargs):
        return ["preimg", "postimg"]
