import copy
import html
import io
import json
import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

import octoprint.filemanager
import octoprint.plugin
import requests
import urllib3
from flask import jsonify
from octoprint.access.permissions import Permissions
from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
from octoprint.server import app
from octoprint.util.version import is_octoprint_compatible
from PIL import Image
from werkzeug.utils import secure_filename

from .commands.commands import Commands
from .emoji import Emoji
from .telegram_notifications import TMSG, telegramMsgDict
from .telegram_utils import TOKEN_REGEX, TelegramUtils, get_chat_title, is_group_or_channel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

get_emoji = Emoji.get_emoji


####################################################
#        TelegramListener Thread Class
# Connects to Telegram and will listen for messages.
# On incoming message the listener will process it.
####################################################


class TelegramListener(threading.Thread):
    def __init__(self, main: "TelegramPlugin"):
        threading.Thread.__init__(self)
        self.update_offset = 0
        self.first_contact = True
        self.main = main
        self.telegram_utils = TelegramUtils(main)
        self.do_stop = False
        self.username = "UNKNOWN"
        self._logger = main._logger.getChild("TelegramListener")

    def run(self):
        self._logger.debug("Try first connect.")
        self.try_first_contact()

        self._logger.debug("Listener is running.")

        # Repeat fetching and processing messages until thread stopped
        while not self.do_stop:
            try:
                self.process_updates()
            except Exception:
                self._logger.exception("Caught and exception calling process_updates.")

        self._logger.debug("Listener exits NOW.")

    # Try to get first contact. Repeat every 120sek if no success or stop if task stopped.
    def try_first_contact(self):
        got_contact = False
        while not self.do_stop and not got_contact:
            try:
                token = self.main._settings.get(["token"])
                self.username = self.main.test_token(token)
                got_contact = True
                self.set_status(f"Connected as {self.username}", ok=True)
            except Exception as e:
                error_message = (
                    f"Caught an exception connecting to telegram: {e}. Waiting 2 minutes before trying again."
                )

                self._logger.exception(error_message)
                self.set_status(error_message)

                time.sleep(120)

    def process_updates(self):
        # Try to check for incoming messages. Wait 120 seconds and repeat on failure.
        try:
            updates = self.get_updates()
        except Exception as e:
            error_message = f"Caught an exception getting updates: {e}. Waiting 2 minutes before trying again."

            self._logger.exception(error_message)
            self.set_status(error_message)

            time.sleep(120)
            return

        for update in updates:
            try:
                self.process_update(update)
            except Exception:
                self._logger.exception("Caught an exception processing a message")

        try:
            if self.main._settings.get(["ForceLoopMessage"]):
                if self.main._printer.is_printing():
                    if self.main.tmsg.is_notification_necessary(None, None):
                        self._logger.debug("ForceLoopMessage on_event StatusPrinting")
                        self.main.on_event("StatusPrinting", {})
        except Exception:
            self._logger.exception("Exception ForceLoopMessage caught!")

        self.set_status(f"Connected as {self.username}", ok=True)
        # We had first contact after octoprint startup so lets send startup message
        if self.first_contact:
            self.first_contact = False
            self.main.on_event("PrinterStart", {})

    def set_update_offset(self, new_value):
        if new_value >= self.update_offset:
            self._logger.debug(f"Updating update_offset from {self.update_offset} to {1 + new_value}")
            self.update_offset = 1 + new_value
        else:
            self._logger.debug(
                f"Not changing update_offset - otherwise would reduce it from {self.update_offset} to {1 + new_value}"
            )

    def process_update(self, update):
        self._logger.debug(f"Processing update: {update}")

        self.set_update_offset(update["update_id"])

        chat_id = self.get_chat_id(update)
        from_id = self.get_from_id(update)

        is_chat_unknown = self.main._settings.get(["chats", chat_id]) is None
        if is_chat_unknown:
            is_enrollment_allowed = (
                self.main.enrollment_countdown_end and datetime.now() <= self.main.enrollment_countdown_end
            )
            if not is_enrollment_allowed:
                self._logger.warning(f"Received an update from unknown chat {chat_id} while enrollment is disabled")
                return

        if "message" in update or "channel_post" in update:
            message = update.get("message", update.get("channel_post"))

            # We got a text message, likely a command
            if "text" in message:
                if is_chat_unknown:
                    self._logger.info(f"Received a text message from unknown chat {chat_id}, enrolling it...")
                    chat = message["chat"]
                    chat_title = get_chat_title(chat)
                    chat_type = chat["type"]
                    self.main.add_chat_to_known_chats(chat_id, chat_title, chat_type)
                else:
                    self.handle_text_message(message, chat_id, from_id)
            # We got a document (file)
            elif "document" in message:
                self.handle_document_message(message, chat_id, from_id)
            # We got message with notification for a new chat title so lets update it
            elif "new_chat_title" in message:
                self.handle_new_chat_title_message(message, chat_id, from_id)
            # We got message with notification for a new chat title photo so lets download it
            elif "new_chat_photo" in message or "delete_chat_photo" in message:
                self.handle_new_chat_photo_message(update, chat_id, from_id)
            # At this point we don't know what message type it is, so we do nothing
            else:
                self._logger.debug(f"Got an unknown message. Doing nothing. Update was: {update}")
        # Triggered when the user clicks on inline buttons
        elif "callback_query" in update:
            self.handle_callback_query(update["callback_query"], chat_id, from_id)
        # Triggered when the bot's role in a chat changes (e.g., added, removed, promoted to admin, blocked in private chat, etc.)
        elif "my_chat_member" in update:
            self.handle_my_chat_member(update["my_chat_member"], chat_id, from_id)
        else:
            self._logger.debug(f"Got an unknown update. Doing nothing. Update was: {update}")

    def handle_my_chat_member(self, my_chat_member, chat_id, from_id):
        new_status = my_chat_member.get("new_chat_member", {}).get("status", "")

        if new_status in ("administrator", "member"):
            # If it is a new chat, add it to the known chats
            if self.main._settings.get(["chats", chat_id]) is None:
                self._logger.info(f"The bot has been added to the new chat {chat_id}, enrolling it...")
                chat = my_chat_member["chat"]
                chat_title = get_chat_title(chat)
                chat_type = chat["type"]
                self.main.add_chat_to_known_chats(chat_id, chat_title, chat_type)

        elif new_status in ("left", "kicked"):
            # The bot left the chat, delete it from known chats
            if self.main._settings.get(["chats", chat_id]) is not None:
                self._logger.info(f"The bot left chat {chat_id}, removing it from settings...")
                self.main.remove_chat_from_known_chats(chat_id)

    def handle_new_chat_title_message(self, message, chat_id, from_id):
        self._logger.info(f"Chat {chat_id} changed title, updating it...")

        chat = message["chat"]

        self.main._settings.set(["chats", chat_id, "title"], get_chat_title(chat))
        self.main._settings.save()
        self.main._plugin_manager.send_plugin_message(
            self.main._identifier, {"type": "update_known_chats", "chats": self.main._settings.get(["chats"])}
        )

    def handle_new_chat_photo_message(self, message, chat_id, from_id):
        self._logger.info(f"Chat {chat_id} changed picture, updating it...")

        try:

            def update_chat_picture():
                public_path = self.main.save_chat_picture(chat_id)
                self.main._settings.set(["chats", chat_id, "image"], public_path)
                self.main._settings.save()
                self.main._plugin_manager.send_plugin_message(
                    self.main._identifier,
                    {"type": "update_known_chats", "chats": self.main._settings.get(["chats"])},
                )

            threading.Thread(target=update_chat_picture, daemon=True).start()
        except Exception:
            self._logger.exception(f"Caught an exception updating chat picture for chat_id {chat_id}")

    def handle_document_message(self, message, chat_id, from_id):
        try:
            self._logger.debug(f"Handling document message: {message}")

            uploaded_file_filename = os.path.basename(message["document"]["file_name"])

            # Check if upload command is allowed
            if not self.main.is_command_allowed(chat_id, from_id, "/upload"):
                self._logger.warning(f"Received file {uploaded_file_filename} from an unauthorized user")
                self.main.send_msg(
                    f"{get_emoji('notallowed')} You are not authorized to upload files!",
                    chatID=chat_id,
                )
                return

            # Check the file extension
            is_zip_file = False
            if not octoprint.filemanager.valid_file_type(uploaded_file_filename, "machinecode"):
                if uploaded_file_filename.lower().endswith(".zip"):
                    is_zip_file = True
                else:
                    self._logger.warning(
                        f"{get_emoji('attention')} Received file {uploaded_file_filename} with invalid extension"
                    )
                    self.main.send_msg(
                        f"{get_emoji('warning')} Sorry, I only accept files with .gcode, .gco or .g or .zip extension",
                        chatID=chat_id,
                    )
                    return

            # Download the uploaded file
            saving_file_response = self.telegram_utils.send_telegram_request(
                f"{self.main.bot_url}/sendMessage",
                "post",
                data={
                    "text": f"{get_emoji('save')} Saving file <code>{html.escape(uploaded_file_filename)}</code>...",
                    "chat_id": chat_id,
                    "parse_mode": "HTML",
                },
            )
            saving_file_msg_id = saving_file_response["result"]["message_id"]

            uploaded_file_content = self.main.get_file(message["document"]["file_id"])

            # Prepare the destination folder
            destination_folder = self.main._file_manager.add_folder(
                octoprint.filemanager.FileDestinations.LOCAL,
                "TelegramPlugin",
                ignore_existing=True,
            )

            # Save the file on disk
            added_files_relative_paths = []
            if is_zip_file:
                zip_file = io.BytesIO(uploaded_file_content)
                with zipfile.ZipFile(zip_file, "r") as zf:
                    for member in zf.infolist():
                        member_filename = os.path.basename(member.filename)

                        try:
                            # Don't extract folders
                            if member.is_dir():
                                self._logger.debug(
                                    f"Ignoring file {member_filename} while extracting a zip because it's a folder"
                                )
                                continue

                            # Don't extract file with invalid extensions
                            if not octoprint.filemanager.valid_file_type(member_filename, "machinecode"):
                                self._logger.debug(
                                    f"Ignoring file {member_filename} while extracting a zip because it has an invalid extension"
                                )
                                continue

                            member_content = zf.read(member)
                            destination_file_relative_path = os.path.join(destination_folder, member_filename)
                            stream_wrapper = octoprint.filemanager.util.StreamWrapper(
                                destination_file_relative_path,
                                io.BytesIO(member_content),
                            )

                            added_file_relative_path = self.main._file_manager.add_file(
                                octoprint.filemanager.FileDestinations.LOCAL,
                                destination_file_relative_path,
                                stream_wrapper,
                                allow_overwrite=True,
                            )
                            self._logger.info(f"Added file to {added_file_relative_path}")

                            added_files_relative_paths.append(destination_file_relative_path)
                        except Exception:
                            self._logger.exception(
                                f"Exception while extracting file {member_filename} contained in the zip"
                            )
            else:
                destination_file_relative_path = os.path.join(destination_folder, uploaded_file_filename)
                stream_wrapper = octoprint.filemanager.util.StreamWrapper(
                    destination_file_relative_path, io.BytesIO(uploaded_file_content)
                )

                added_file_relative_path = self.main._file_manager.add_file(
                    octoprint.filemanager.FileDestinations.LOCAL,
                    destination_file_relative_path,
                    stream_wrapper,
                    allow_overwrite=True,
                )
                self._logger.info(f"Added file to {added_file_relative_path}")

                added_files_relative_paths.append(added_file_relative_path)

            # Update the "saving file" message
            command_buttons = None
            if added_files_relative_paths:
                response_message = (
                    f"{get_emoji('download')} I've successfully saved the file"
                    f"{'s' if len(added_files_relative_paths) > 1 else ''} you sent me as "
                    f"{', '.join(f'<code>{html.escape(path)}</code>' for path in added_files_relative_paths)}."
                )

                if self.main._settings.get(["selectFileUpload"]) and len(added_files_relative_paths) == 1:
                    # Check if printer is ready
                    if not self.main._printer.is_ready():
                        response_message += (
                            f"\n{get_emoji('attention')} But I couldn't load it because the printer is not ready."
                        )
                    else:
                        # Load the uploaded file
                        try:
                            file_to_select_abs_path = self.main._file_manager.path_on_disk(
                                octoprint.filemanager.FileDestinations.LOCAL,
                                added_files_relative_paths[0],
                            )
                            self._logger.debug(f"Selecting file: {file_to_select_abs_path}")
                            self.main._printer.select_file(file_to_select_abs_path, sd=False, printAfterSelect=False)

                            # Ask the user whether to print the loaded file
                            response_message += (
                                f"\n{get_emoji('check')} And loaded it.\n"
                                f"{get_emoji('question')} Do you want me to start printing it now?"
                            )
                            command_buttons = [
                                [
                                    [
                                        f"{get_emoji('check')} Print",
                                        "/print_y",
                                    ],
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "close",
                                    ],
                                ]
                            ]
                        except Exception:
                            response_message += f"\n{get_emoji('attention')} But I wasn't able to load the file."
            else:
                response_message = f"{get_emoji('warning')} No files were added. Did you upload an empty zip?"

            self.main.send_msg(
                response_message,
                chatID=chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=saving_file_msg_id,
            )
        except Exception:
            self._logger.exception("Caught an exception in handle_document_message")
            self.main.send_msg(
                (
                    f"{get_emoji('attention')} Something went wrong during processing of your file.\n"
                    f"Sorry. More details are in log files."
                ),
                chatID=chat_id,
            )

    def handle_text_message(self, message, chat_id, from_id):
        message_text = message["text"]

        if not message_text.startswith("/"):
            self._logger.debug(f"Ignoring text message '{message_text}' because it doesn't start with a slash")
            return

        # Remove bot username from commands like /command@botusername
        command = message_text.split("@")[0]

        self.handle_command(command, chat_id, from_id, message.get("from"))

    def handle_callback_query(self, callback_query, chat_id, from_id):
        command = callback_query["data"]
        from_obj = callback_query["from"]
        msg_id_to_update = callback_query.get("message", {}).get("message_id", "")

        # Handle callback query data as if it was a text command
        try:
            self.handle_command(command, chat_id, from_id, from_obj, msg_id_to_update)
        except Exception:
            self._logger.exception("Caught an exception calling handle_text_message")

        # Answer callback query (to prevent inline buttons from continuing to blink)
        try:
            self.main.telegram_utils.send_telegram_request(
                f"{self.main.bot_url}/answerCallbackQuery",
                "post",
                data={"callback_query_id": callback_query["id"]},
            )
        except Exception:
            self._logger.exception("Caught an exception sending answerCallbackQuery")

    def handle_command(self, command, chat_id, from_id, from_obj, msg_id_to_update=""):
        # Separate command and parameter
        parts = command.split("_")
        command = parts[0].lower()
        cmd_info = self.main.commands.commands_dict.get(command, {})
        parameter = "_".join(parts[1:]) if cmd_info.get("param") else ""

        # Log received command
        self._logger.info(
            f"Received command '{command}' with parameter '{parameter}' in chat '{chat_id}' from '{from_id}'"
        )

        # Is command  known?
        if command not in self.main.commands.commands_dict:
            # we dont know the command so skip the message
            self._logger.warning("Previous command was an unknown command.")
            if not self.main._settings.get(["no_mistake"]):
                self.main.send_msg(
                    f"{get_emoji('notallowed')} I do not understand you!",
                    chatID=chat_id,
                )
            return

        # Check if user is allowed to execute the command
        if self.main.is_command_allowed(chat_id, from_id, command):
            # Identify user
            user = "Telegram - "
            try:
                username = from_obj.get("username")

                first_name = from_obj.get("first_name")
                last_name = from_obj.get("last_name")
                fullname = " ".join(part for part in (first_name, last_name) if part).strip()

                parts = []

                if username:
                    parts.append(f"@{username}")
                if fullname:
                    parts.append(fullname)

                user += " - ".join(parts) if parts else "UNKNOWN"
            except Exception:
                user += "UNKNOWN"

            # Execute command
            try:
                self.main.commands.run_command(command, chat_id, from_id, parameter, msg_id_to_update, user)
            except Exception:
                self._logger.exception(f"Caught an exception executing command {command}")
                self.main.send_msg(
                    f"{get_emoji('attention')} Error executing your command! Please check logs.",
                    chatID=chat_id,
                    msg_id=msg_id_to_update,
                )
        else:
            # User was not allowed to execute this command
            self._logger.warning("Previous command was from an unauthorized user.")
            self.main.send_msg(
                f"{get_emoji('notallowed')} You are not allowed to do this!",
                chatID=chat_id,
            )

    def get_chat_id(self, update):
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
        elif "callback_query" in update:
            chat_id = update["callback_query"]["message"]["chat"]["id"]
        elif "my_chat_member" in update:
            chat_id = update["my_chat_member"]["chat"]["id"]
        elif "channel_post" in update:
            chat_id = update["channel_post"]["chat"]["id"]
        else:
            raise ValueError(
                "Unsupported update type: no 'message' or 'callback_query' or 'my_chat_member' or 'channel_post' found"
            )

        return str(chat_id)

    def get_from_id(self, update):
        if "message" in update:
            from_id = update.get("message", {}).get("from", {}).get("id", "")
        elif "callback_query" in update:
            from_id = update.get("callback_query", {}).get("from", {}).get("id", "")
        elif "my_chat_member" in update:
            from_id = update.get("my_chat_member", {}).get("from", {}).get("id", "")
        elif "channel_post" in update:
            from_id = update.get("channel_post", {}).get("from", {}).get("id", "")
        else:
            raise ValueError("Unsupported update type: no 'message' or 'callback_query' or 'my_chat_member' found")

        return str(from_id)

    def get_updates(self):
        # If it is the first contact, drain the updates backlog
        if self.update_offset == 0 and self.first_contact:
            while True:
                json_data = self.telegram_utils.send_telegram_request(
                    f"{self.main.bot_url}/getUpdates",
                    "get",
                    params={"offset": self.update_offset, "timeout": 0},
                )

                results = json_data["result"]

                if results and "update_id" in results[0]:
                    self.set_update_offset(results[0]["update_id"])

                if not results:
                    self._logger.debug("Ignored all messages until now because first_contact was True.")
                    break

            if self.update_offset == 0:
                self.set_update_offset(0)

        # Else, get the updates
        else:
            json_data = self.telegram_utils.send_telegram_request(
                f"{self.main.bot_url}/getUpdates",
                "get",
                params={"offset": self.update_offset, "timeout": 30},
            )

        # Update update_offset
        results = json_data["result"]
        for entry in results:
            self.set_update_offset(entry["update_id"])

        # Return results
        return results

    # Stop the listener
    def stop(self):
        self.do_stop = True

    def set_status(self, status, ok=False):
        if self.main.connection_state_str == status:
            return

        if self.do_stop:
            self._logger.debug(f"Would set status but do_stop is True: {status}")
            return

        self._logger.debug(f"Setting status: {status}")
        self.connection_ok = ok
        self.main.connection_state_str = status


class RedactingFormatter(logging.Formatter):
    # Redact Telegram bot tokens from logs
    def format(self, record):
        try:
            formatted = super().format(record)
            return TOKEN_REGEX.sub("REDACTED", formatted)
        except Exception as e:
            return f"RedactingFormatter failed: {type(e).__name__}"


class WebcamProfile:
    def __init__(
        self,
        name: Optional[str] = None,
        snapshot: Optional[str] = None,
        snapshotTimeout: Optional[int] = 15,
        stream: Optional[str] = None,
        flipH: bool = False,
        flipV: bool = False,
        rotate90: bool = False,
    ):
        self.name = name
        self.snapshot = snapshot
        self.snapshotTimeout = snapshotTimeout
        self.stream = stream
        self.flipH = flipH
        self.flipV = flipV
        self.rotate90 = rotate90

    def __repr__(self):
        return (
            f"<WebcamProfile name={self.name!r} snapshot={self.snapshot!r}  snapshotTimeout={self.snapshotTimeout!r}"
            f"stream={self.stream!r} flipH={self.flipH} "
            f"flipV={self.flipV} rotate90={self.rotate90}>"
        )


########################################
########################################
############## THE PLUGIN ##############
########################################
########################################
class TelegramPlugin(
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.WizardPlugin,
):
    # For more init stuff see also on_after_startup()
    def __init__(self):
        self._logger = logging.getLogger("octoprint.plugins.telegram")
        self.thread = None
        self.port = 5000
        self.bot_ready = False
        self.bot_url = None
        self.connection_state_str = "Disconnected."
        self.connection_ok = False

        self.shut_up = set()

        self.commands = Commands(self)
        self.telegram_utils = None
        self.tmsg = None

        self.new_chat_settings = {}  # Initial settings for new chat. See on_after_startup()

        self.enrollment_countdown_end = None

        self.user_pause_already_notified = False

    # Starts the telegram bot
    def start_bot(self):
        token = self._settings.get(["token"])

        if token and self.thread is None:
            self._logger.debug("Starting bot.")

            self.bot_url = f"https://api.telegram.org/bot{token}"
            self.bot_file_url = f"https://api.telegram.org/file/bot{token}"

            self.thread = TelegramListener(self)
            self.thread.daemon = True
            self.thread.start()

            self.bot_ready = True

            # Set bot commands
            try:
                self.set_bot_commands()
            except Exception:
                self._logger.exception("Caught an exception setting bot commands")

            # Update chats
            try:

                def _update_chats():
                    for chat_id, chat_settings in self._settings.get(["chats"]).items():
                        if chat_id == "zBOTTOMOFCHATS":
                            continue

                        # Delete unreachable chats
                        if chat_settings.get("type") == "private":
                            endpoint = f"{self.bot_url}/sendChatAction"
                            params = {"chat_id": chat_id, "action": "typing"}
                        else:
                            endpoint = f"{self.bot_url}/getChat"
                            params = {"chat_id": chat_id}
                        try:
                            self.telegram_utils.send_telegram_request(
                                endpoint,
                                "get",
                                params=params,
                                timeout=5,
                            )
                        except Exception as e:
                            if '"error_code":403' in getattr(e, "telegram_response_text", ""):
                                self._logger.info(f"Chat {chat_id} is unreachable, removing it from settings...")
                                self.remove_chat_from_known_chats(chat_id)
                                continue

                        # Update chat pictures
                        public_path = self.save_chat_picture(chat_id)
                        self._settings.set(["chats", chat_id, "image"], public_path)

                    # Save settings and update known chats table
                    self._settings.save()
                    self._plugin_manager.send_plugin_message(
                        self._identifier, {"type": "update_known_chats", "chats": self._settings.get(["chats"])}
                    )

                threading.Thread(target=_update_chats, daemon=True).start()
            except Exception:
                self._logger.exception("Caught an exception updating chats")

    # Stops the telegram bot
    def stop_bot(self):
        if self.thread is not None:
            self._logger.debug("Stopping bot.")

            self.bot_ready = False

            self.bot_url = None
            self.bot_file_url = None

            self.thread.stop()
            self.thread = None

    ##########
    ### Asset API
    ##########

    def get_assets(self):
        return dict(
            js=["js/telegram.js"],
            css=["css/telegram.css"],
        )

    def get_tmpgif_dir(self):
        return os.path.join(self.get_plugin_data_folder(), "tmpgif")

    ##########
    ### Template API
    ##########

    def get_template_configs(self):
        return [dict(type="settings", name="Telegram", custom_bindings=True)]

    def get_template_vars(self):
        return {"custom_emoji_map": Emoji.get_custom_emoji_map(), "plugin_version": self._plugin_version}

    ##########
    ### Wizard API
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
    ### Startup/Shutdown API
    ##########

    def on_startup(self, host, port):
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

        # Set port
        self.port = port

    def on_after_startup(self):
        Emoji.init(self._settings)
        app.jinja_env.filters["telegram_emoji"] = Emoji.get_emoji

        self.telegram_utils = TelegramUtils(self)

        # Notification Message Handler class. Called only by on_event()
        self.tmsg = TMSG(self)

        # Initial settings for new chat.
        self.new_chat_settings = {
            "title": "[UNKNOWN]",
            "accept_commands": False,
            "send_notifications": False,
            "type": "private",
            "image": "",
            "allow_users": False,
            "commands": {k: False for k, v in self.commands.commands_dict.items() if "bind_none" not in v},
            "notifications": {k: False for k, v in telegramMsgDict.items()},
        }

        # Create / clean tmpgif folder
        shutil.rmtree(self.get_tmpgif_dir(), ignore_errors=True)
        os.makedirs(self.get_tmpgif_dir(), exist_ok=True)

        self.start_bot()

    def on_shutdown(self):
        self.on_event("PrinterShutdown", {})
        self.stop_bot()

    ##########
    ### Settings API
    ##########

    def get_settings_defaults(self):
        return dict(
            token="",
            notification_height=5.0,
            notification_time=15,
            message_at_print_done_delay=0,
            messages=telegramMsgDict,
            # zBOTTOMOFCHATS is a dummy element to avoid bug https://github.com/OctoPrint/OctoPrint/issues/5177
            chats={"zBOTTOMOFCHATS": {}},
            send_icon=True,
            send_gif=False,
            no_mistake=False,
            sort_files_by_date=False,
            no_cpulimit=False,
            ffmpeg_preset="medium",
            PreImgMethod="None",
            PreImgCommand="",
            PreImgDelay=0,
            PostImgMethod="None",
            PostImgCommand="",
            PostImgDelay=0,
            TimeFormat="%H:%M:%S",
            DayTimeFormat="%a %H:%M:%S",
            WeekTimeFormat="%d.%m.%Y %H:%M:%S",
        )

    def get_settings_preprocessors(self):
        return (
            dict(),
            dict(
                notification_height=lambda x: float(x),
                notification_time=lambda x: int(x),
            ),
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
        self._logger.warning(f"Migration - start migration from {current} to {target}")

        chats = {k: v for k, v in self._settings.get(["chats"]).items() if k != "zBOTTOMOFCHATS"}
        self._logger.info(f"Migration - loaded chats: {chats}")

        messages = self._settings.get(["messages"])
        self._logger.info(f"Migration - loaded notification messages: {messages}")

        # Migrate from plugin versions < 1.3.0
        if current is None or current < 1:
            # Is there a chat from old single user plugin version? Then migrate it into chats.
            chat = self._settings.get(["chat"])
            if chat is not None:
                new_chat_settings = copy.deepcopy(self.new_chat_settings)
                # Try to get info from telegram by sending a migration message
                try:
                    message = {
                        "text": (
                            f"The OctoPrint Plugin {self._plugin_name} has been updated to new version {self._plugin_version}.\n\n"
                            f"Please open your {self._plugin_name} settings in OctoPrint and configure this chat.\n\n"
                            "Until then, you will not be able to send or receive anything useful with this Bot.\n\n"
                            "More information on: https://github.com/jacopotediosi/OctoPrint-Telegram"
                        ),
                        "chat_id": chat,
                        "disable_web_page_preview": True,
                    }

                    json_data = self.telegram_utils.send_telegram_request(
                        f"{self.bot_url}/sendMessage",
                        "post",
                        data=message,
                    )

                    chat = json_data["result"]["chat"]
                    new_chat_settings["title"] = get_chat_title(chat)
                except Exception:
                    self._logger.exception(
                        "Caught an exception migrating from the single chat version. Done with defaults."
                    )

                # Place the migrated chat in chats
                self._settings.set(["chat"], None)
                chats[str(chat["id"])] = new_chat_settings

        # Migrate from plugin versions < 1.10.0
        if current is None or current < 7:
            # In previous versions, "type" was stored in uppercase
            for chat_settings in chats.values():
                if "type" in chat_settings and isinstance(chat_settings["type"], str):
                    chat_settings["type"] = chat_settings["type"].lower()

        # General migration from all previous versions
        if current is None or current < target:
            # Rename mappings (old:new)
            commands_to_rename = {"/list": "/files", "/imsorrydontshutup": "/dontshutup", "/on": "/power"}
            notifications_to_rename = {
                "TelegramSendNotPrintingStatus": "StatusNotPrinting",
                "TelegramSendPrintingStatus": "StatusPrinting",
                "plugin_pause_for_user_event_notify": "PausedForUser",
            }
            settings_to_rename = {"fileOrder": "sort_files_by_date"}

            # Settings to delete
            settings_to_delete = [
                "message_at_startup",
                "message_at_shutdown",
                "message_at_print_started",
                "message_at_print_done",
                "message_at_print_failed",
                "image_not_connected",
                "gif_not_connected",
            ]

            # Update chats
            for chat_settings in chats.values():
                # Add new chat settings
                for setting, default_value in self.new_chat_settings.items():
                    if setting not in chat_settings:
                        chat_settings[setting] = copy.deepcopy(default_value)

                # Get references
                chat_commands = chat_settings["commands"]
                chat_notifications = chat_settings["notifications"]

                # Rename commands (copy, not move)
                for old_command, new_command in commands_to_rename.items():
                    if old_command in chat_commands:
                        chat_commands[new_command] = chat_commands[old_command]

                # Remove obsolete commands (marked with 'bind_none' or no longer present in commands_dict)
                for command in list(chat_commands):
                    if command not in self.commands.commands_dict or "bind_none" in self.commands.commands_dict.get(
                        command, {}
                    ):
                        chat_commands.pop(command, None)

                # Add new commands
                for command, command_props in self.commands.commands_dict.items():
                    if command not in chat_commands and "bind_none" not in command_props:
                        chat_commands[command] = False

                # Rename notifications (copy, not move)
                for old_notification, new_notification in notifications_to_rename.items():
                    if old_notification in chat_notifications:
                        chat_notifications[new_notification] = chat_notifications[old_notification]

                # Remove obsolete notifications (no longer present in telegramMsgDict)
                for msg in list(chat_notifications):
                    if msg not in telegramMsgDict:
                        chat_notifications.pop(msg, None)

                # Add new notifications
                for notification in telegramMsgDict:
                    if notification not in chat_notifications:
                        chat_notifications[notification] = False

            # Rename notification messages (copy, not move)
            for message, message_props in list(messages.items()):
                mapped_key = notifications_to_rename.get(message, message)
                messages[mapped_key] = (
                    message_props
                    if isinstance(message_props, dict)
                    else {**telegramMsgDict.get(mapped_key, {}), "text": str(message_props)}
                )

            # Remove obsolete notification messages (no longer present in telegramMsgDict)
            for message in list(messages):
                if message not in telegramMsgDict:
                    messages.pop(message, None)

            # Add new messages
            for message, message_props in telegramMsgDict.items():
                if message not in messages:
                    messages[message] = message_props

            # Rename settings
            for old_setting, new_setting in settings_to_rename.items():
                old_setting_value = self._settings.get([old_setting])
                if old_setting_value is not None:
                    self._settings.set([new_setting], old_setting_value)
                    self._settings.set([old_setting], None)

            # Delete old settings
            for key in settings_to_delete:
                self._settings.set([key], None)

        # Save the settings after migration is done
        self._settings.set(["chats"], chats)
        self._logger.info(f"Migration - chats set: {chats}")
        self._settings.set(["messages"], messages)
        self._logger.info(f"Migration - notification messages set: {messages}")

        self._logger.warning("Migration - end")

    def on_settings_save(self, data):
        self._logger.debug(f"Saving data: {data}")

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
                self.connection_state_str = "The previously entered token doesn't seem to have the correct format. It should look like this: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11."

        # Now save settings
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

        # Reconnect if the token changed
        if "token" in data and data["token"] != old_token:
            self.stop_bot()
            self.start_bot()

    def get_settings_restricted_paths(self):
        # Only used in OctoPrint versions > 1.2.16
        return dict(admin=[["token"], ["chats"]])

    ##########
    ### Softwareupdate API
    ##########

    def get_update_information(self, *args, **kwargs):
        return dict(
            telegram=dict(
                displayName=self._plugin_name,
                displayVersion=self._plugin_version,
                type="github_release",
                current=self._plugin_version,
                user="jacopotediosi",
                repo="OctoPrint-Telegram",
                pip="https://github.com/jacopotediosi/OctoPrint-Telegram/archive/{target_version}.zip",
            )
        )

    ##########
    ### Custom Event Hook
    ##########

    def register_custom_events(*args, **kwargs):
        return ["preimg", "postimg"]

    ##########
    ### EventHandler API
    ##########

    def on_event(self, event, payload, **kwargs):
        try:
            if not self.tmsg:
                self._logger.debug("Received an event, but tmsg is not initialized yet")
                return

            if not self.bot_ready:
                self._logger.warning("Received an event, but bot is not ready")
                return

            # If we know the event, start handler
            if event in self.tmsg.msgCmdDict:
                self._logger.debug(f"Received a known event: {event} - Payload: {payload}")
                self.tmsg.startEvent(event, payload, **kwargs)
        except Exception:
            self._logger.exception("Caught an exception handling an event")

    ##########
    ### TemplatePlugin mixin
    ##########

    def is_template_autoescaped(self):
        return True

    ##########
    ### SimpleApi API
    ##########

    def is_api_protected(self):
        return True

    def on_api_get(self, request):
        if not Permissions.SETTINGS.can():
            return "Insufficient permissions", 403

        return self.process_on_api_get(request.args)

    def process_on_api_get(self, request_args=None):
        # /?enrollmentCountdown
        if request_args and "enrollmentCountdown" in request_args:
            if self.enrollment_countdown_end:
                remaining = int((self.enrollment_countdown_end - datetime.now()).total_seconds())
                if remaining > 0:
                    return jsonify({"remaining": remaining})
            return jsonify({"remaining": 0})

        # /?bindings
        if request_args and "bindings" in request_args:
            bind_text = {}
            for key, value in telegramMsgDict.items():
                if "bind_msg" in value:
                    msg_key = value["bind_msg"]
                    bind_text.setdefault(msg_key, []).append({key: value.get("desc", "No description provided")})
            return jsonify(
                {
                    "bind_cmd": {
                        k: v.get("desc", "No description provided")
                        for k, v in self.commands.commands_dict.items()
                        if "bind_none" not in v
                    },
                    "bind_msg": {
                        k: v.get("desc", "No description provided")
                        for k, v in telegramMsgDict.items()
                        if "bind_msg" not in v
                    },
                    "bind_text": bind_text,
                    "no_setting": [k for k, v in telegramMsgDict.items() if "no_setting" in v],
                }
            )

        # /?default_messages
        if request_args and "default_messages" in request_args:
            return jsonify(telegramMsgDict)

        # /?requirements
        if request_args and "requirements" in request_args:
            settings_ffmpeg = self._settings.global_get(["webcam", "ffmpeg"])
            ffmpeg_path = (
                settings_ffmpeg
                if isinstance(settings_ffmpeg, str)
                and os.path.isfile(settings_ffmpeg)
                and os.access(settings_ffmpeg, os.X_OK)
                else shutil.which("ffmpeg")
            )

            cpulimiter_path = shutil.which("cpulimit") or shutil.which("limitcpu")

            def get_plugin_status(plugin_id):
                info = self._plugin_manager.get_plugin_info(plugin_id, require_enabled=False)
                if info is None:
                    return "not_installed"
                if not info.enabled:
                    return "disabled"
                return "enabled"

            suggested_plugin_ids = [
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
                "prusaslicerthumbnails",
                "psucontrol",
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
            ]

            return jsonify(
                {
                    "ffmpeg_path": ffmpeg_path,
                    "cpulimiter_path": cpulimiter_path,
                    **{id: get_plugin_status(id) for id in suggested_plugin_ids},
                }
            )

        # /
        ret_chats = {k: v for k, v in self._settings.get(["chats"]).items() if k != "zBOTTOMOFCHATS"}

        return jsonify(
            {
                "chats": ret_chats,
                "connection_state_str": self.connection_state_str,
                "connection_ok": self.connection_ok,
            }
        )

    def get_api_commands(self):
        return dict(
            delChat=["chat_id"],
            editChat=[
                "chat_id",
                "accept_commands",
                "send_notifications",
                "allow_users",
            ],
            startEnrollmentCountdown=[],
            stopEnrollmentCountdown=[],
            testEvent=["event"],
            testToken=["token"],
        )

    def on_api_command(self, command, data):
        self._logger.info(f"Received API command {command} with data {data}")

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
                username = self.test_token(token_to_test)

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

            is_chat_unknown = self._settings.get(["chats", chat_id]) is None
            if is_chat_unknown:
                self._logger.warning(f"Chat id {chat_id} is unknown")
                return jsonify({"ok": False, "error": "Unknown chat with given id"}), 404

            try:
                self.remove_chat_from_known_chats(chat_id)
                self._logger.info(f"Chat {chat_id} has been deleted via API")
            except Exception:
                self._logger.exception("Caught an exception in delChat API command")
                return jsonify({"ok": False, "error": "Cannot delete chat, please check logs"}), 500

            # Return updated chats settings
            return self.process_on_api_get()

        elif command == "testEvent":
            event = data.get("event")
            try:
                self.on_event(event, {})
                self._logger.info(f"Event {event} tested")
                return jsonify({"ok": True})
            except Exception:
                self._logger.exception(f"Caught an exception testing event {event}")
                return jsonify({"ok": False})

        elif command == "editChat":
            chat_id = str(data.get("chat_id"))
            settings_chat = self._settings.get(["chats", chat_id])

            # Check if chat is unknown
            if not settings_chat:
                self._logger.warning(f"Chat id {chat_id} is unknown")
                return jsonify({"ok": False, "error": "Unknown chat with given id"}), 404

            settings_keys = ("accept_commands", "send_notifications", "allow_users")

            # Check that settings_keys are boolean
            invalid_keys = [k for k in settings_keys if not isinstance(data.get(k), bool)]
            if invalid_keys:
                self._logger.warning(f"Received args {', '.join(invalid_keys)} are not boolean")
                return jsonify(
                    {"ok": False, "error": f"Invalid values: {', '.join(invalid_keys)} must be boolean"}
                ), 400

            # Update user
            for key in settings_keys:
                settings_chat[key] = data[key]
            self._settings.set(["chats", chat_id], settings_chat)
            self._settings.save()

            # Logging successful user update
            settings = ", ".join(f"{k}={data[k]}" for k in settings_keys)
            self._logger.info(f"Updated settings for chat {chat_id} - {settings}")

            # Return updated chats settings
            return self.process_on_api_get()

        elif command == "startEnrollmentCountdown":
            duration = 5 * 60
            self.enrollment_countdown_end = datetime.now() + timedelta(seconds=duration)
            self._plugin_manager.send_plugin_message(
                self._identifier, {"type": "enrollment_countdown", "remaining": duration}
            )
            return jsonify({"ok": True, "duration": duration})

        elif command == "stopEnrollmentCountdown":
            self.enrollment_countdown_end = None
            self._plugin_manager.send_plugin_message(self._identifier, {"type": "enrollment_countdown", "remaining": 0})
            return jsonify({"ok": True})

    ##########
    ### Telegram API-Functions
    ##########

    def send_msg(self, message, **kwargs):
        if not self.bot_ready:
            return

        settings_chats = self._settings.get(["chats"])

        kwargs["message"] = message

        try:
            # Message is a regular event notification
            if "chatID" not in kwargs and "event" in kwargs:
                event = kwargs["event"]

                self._logger.debug(f"Send_msg() - Found event: {event} | chats settings={settings_chats}")

                for chat_id, chat_settings in settings_chats.items():
                    if chat_id == "zBOTTOMOFCHATS":
                        continue

                    try:
                        notifications = chat_settings.get("notifications", {})
                        send_notifications = chat_settings.get("send_notifications", False)
                        is_shut_up = str(chat_id) in self.shut_up

                        if notifications.get(event) and send_notifications and not is_shut_up:
                            kwargs["chatID"] = chat_id
                            threading.Thread(target=self._send_msg, kwargs=kwargs).run()
                    except Exception:
                        self._logger.exception(f"Caught an exception processing chat {chat_id}")

            # Message is a broadcast
            elif "chatID" not in kwargs:
                for chat_id in settings_chats:
                    if chat_id == "zBOTTOMOFCHATS":
                        continue

                    try:
                        kwargs["chatID"] = chat_id
                        threading.Thread(target=self._send_msg, kwargs=kwargs).run()
                    except Exception:
                        self._logger.exception(f"Caught an exception processing chat {chat_id}")

            # Message is a 'editMessageText'
            elif kwargs.get("msg_id"):
                threading.Thread(target=self._send_edit_msg, kwargs=kwargs).run()

            # Message is a direct message
            else:
                threading.Thread(target=self._send_msg, kwargs=kwargs).run()
        except Exception:
            self._logger.exception("Caught an exception in send_msg()")

    # Edits the text of an existing message (by msg_id) previously sent.
    # Automatically called by send_msg() when a valid msg_id is provided.
    def _send_edit_msg(
        self,
        message="",
        msg_id="",
        chatID="",
        responses=None,
        markup="off",
        delay=0,
        **kwargs,
    ):
        if not self.bot_ready:
            return

        if delay > 0:
            time.sleep(delay)
        try:
            self._logger.debug(f"Sending a message UPDATE in chat {chatID}: {message}")
            data = {}
            data["text"] = message
            data["message_id"] = msg_id
            data["chat_id"] = int(chatID)
            if markup != "off":
                if markup in {"HTML", "Markdown", "MarkdownV2"}:
                    data["parse_mode"] = markup
                else:
                    self._logger.warning(f"Invalid markup: {markup}")
            if responses:
                my_arr = []
                for k in responses:
                    my_arr.append([{"text": x[0], "callback_data": x[1]} for x in k])
                keyboard = {"inline_keyboard": my_arr}
                data["reply_markup"] = json.dumps(keyboard)

            self._logger.debug(f"SENDING UPDATE: {data}")
            self.telegram_utils.send_telegram_request(
                f"{self.bot_url}/editMessageText",
                "post",
                data=data,
            )

        except Exception as e:
            if "Bad Request: message is not modified" not in getattr(e, "telegram_response_text", ""):
                self._logger.exception("Caught an exception in _send_edit_msg()")
                self.thread.set_status("Exception sending a message")
                self.telegram_utils.send_telegram_request(
                    f"{self.bot_url}/sendMessage",
                    "post",
                    data={
                        "chat_id": chatID,
                        "text": "I tried to send you a message, but an exception occurred. Please check the logs.",
                    },
                )

    def _send_msg(
        self,
        message="",
        with_image=False,
        with_gif=False,
        responses=None,
        delay=0,
        chatID="",
        markup="off",
        show_web=False,
        silent=False,
        gif_duration=5,
        **kwargs,
    ):
        self._logger.debug(f"Start _send_msg with args: {locals()}")

        try:
            # Check if bot is ready
            if not self.bot_ready:
                return

            # Delay
            if delay > 0:
                self._logger.debug(f"Sleeping {delay} seconds")
                time.sleep(delay)

            # Preparing message data
            message_data = {}

            message_data["disable_web_page_preview"] = not show_web
            message_data["chat_id"] = chatID
            message_data["disable_notification"] = silent

            if markup != "off":
                if markup == "HTML" or markup == "Markdown" or markup == "MarkdownV2":
                    message_data["parse_mode"] = markup
                else:
                    self._logger.warning(f"Invalid markup: {markup}")

            if responses:
                inline_keyboard_buttons = []
                for k in responses:
                    inline_keyboard_buttons.append([{"text": x[0], "callback_data": x[1]} for x in k])
                inline_keyboard = {"inline_keyboard": inline_keyboard_buttons}
                message_data["reply_markup"] = json.dumps(inline_keyboard)

            # Prepare images and gifs to send
            images_to_send = []
            gifs_to_send = []

            # Add thumbnail to images to send
            thumbnail = kwargs.get("thumbnail")
            if thumbnail:
                try:
                    self._logger.debug(f"Get thumbnail: {thumbnail}")
                    thumbnail_response = self.send_octoprint_request(f"/{thumbnail}")
                    images_to_send.append(thumbnail_response.content)
                except Exception:
                    self._logger.exception("Caught an exception getting thumbnail")

            # Add movie to gifs to send
            movie = kwargs.get("movie")
            if movie:
                if os.path.getsize(movie) > 50 * 1024 * 1024:
                    self._logger.warning("Skipping movie because it is bigger than 50MB")
                    message += (
                        ("<br>" if markup == "HTML" else "\n")
                        + "The timelapse/Octolapse video could not be sent via Telegram because its size exceeds 50MB. "
                        "Please download it manually from the OctoPrint web interface."
                    )
                else:
                    gifs_to_send.append(movie)

            if with_image or with_gif:
                with self.telegram_action_context(chatID, "record_video"):
                    # Pre image
                    try:
                        self.pre_image()
                    except Exception:
                        self._logger.exception("Caught an exception calling pre_image()")

                    # Add webcam images to images to send
                    if with_image:
                        try:
                            images_to_send += self.take_all_images()
                        except Exception:
                            self._logger.exception("Caught an exception taking all images")

                    # Add gifs to gifs to send
                    if with_gif:
                        try:
                            gifs_to_send += self.take_all_gifs(gif_duration)
                        except Exception:
                            self._logger.exception("Caught an exception taking all gifs")

                    # Post image
                    try:
                        self.post_image()
                    except Exception:
                        self._logger.exception("Caught an exception calling post_image()")

            # Initialize files and media
            files = {}
            media = []

            # Add images to send to files and media
            for i, image_to_send in enumerate(images_to_send):
                if len(image_to_send) > 50 * 1024 * 1024:
                    self._logger.warning("Skipping an image bigger than 50MB")
                    continue

                files[f"photo_{i}"] = image_to_send

                input_media_photo = {
                    "type": "photo",
                    "media": f"attach://photo_{i}",
                }

                if len(media) == 0 and message != "":
                    input_media_photo["caption"] = message
                    if message_data.get("parse_mode"):
                        input_media_photo["parse_mode"] = message_data["parse_mode"]

                media.append(input_media_photo)

            # Add gifs to send to files and media
            for i, gif_to_send in enumerate(gifs_to_send):
                try:
                    if os.path.getsize(gif_to_send) > 50 * 1024 * 1024:
                        self._logger.warning("Skipping a gif bigger than 50MB")
                        continue

                    with open(gif_to_send, "rb") as gif_file:
                        files[f"video_{i}"] = gif_file.read()

                    input_media_video = {
                        "type": "video",
                        "media": f"attach://video_{i}",
                    }

                    if len(media) == 0 and message != "":
                        input_media_video["caption"] = message
                        if message_data.get("parse_mode"):
                            input_media_video["parse_mode"] = message_data["parse_mode"]

                    media.append(input_media_video)
                except Exception:
                    self._logger.exception("Caught an exception reading gif file")

            # If there are media, send a media-group message
            if media:
                self._logger.debug(f"Sending message with media, chat id: {chatID}")

                if gifs_to_send:
                    action = "upload_video"
                else:
                    action = "upload_photo"
                with self.telegram_action_context(chatID, action):
                    message_data["media"] = json.dumps(media)

                    tlg_response = self.telegram_utils.send_telegram_request(
                        f"{self.bot_url}/sendMediaGroup",
                        "post",
                        data=message_data,
                        files=files,
                    )

            # If there aren't media, send a text-only message
            else:
                self._logger.debug(f"Sending text-only message, chat id: {chatID}")

                with self.telegram_action_context(chatID, "typing"):
                    message_data["text"] = message

                    tlg_response = self.telegram_utils.send_telegram_request(
                        f"{self.bot_url}/sendMessage",
                        "post",
                        data=message_data,
                    )

        except Exception:
            self._logger.exception("Caught an exception in _send_msg()")
            self.thread.set_status("Exception sending a message")
            self.telegram_utils.send_telegram_request(
                f"{self.bot_url}/sendMessage",
                "post",
                data={
                    "chat_id": chatID,
                    "text": "I tried to send you a message, but an exception occurred. Please check the logs.",
                },
            )

    def send_file(self, chat_id, path, caption=""):
        if not self.bot_ready:
            return

        self._logger.info(f"Sending file {path} to chat {chat_id}")

        if os.path.getsize(path) > 50 * 1024 * 1024:
            self._logger.warning(f"File '{path}' not sent to chat {chat_id}: exceeds 50MB limit")

            self.send_msg(
                f"{get_emoji('warning')} The file `{os.path.basename(path)}` is too large (>50MB) to send via Telegram. "
                "Please download it manually from the OctoPrint web interface.",
                chatID=chat_id,
            )
            return

        with self.telegram_action_context(chat_id, "upload_document"):
            with open(path, "rb") as document:
                self.telegram_utils.send_telegram_request(
                    f"{self.bot_url}/sendDocument",
                    "post",
                    files={"document": document},
                    data={"chat_id": chat_id, "caption": caption},
                )

    def get_file(self, file_id):
        if not self.bot_ready:
            return

        self._logger.debug(f"Requesting file with id {file_id}")

        json_data = self.telegram_utils.send_telegram_request(
            f"{self.bot_url}/getFile",
            "get",
            data={"file_id": file_id},
        )

        file_path = json_data["result"]["file_path"]
        file_url = f"{self.bot_file_url}/{file_path}"

        self._logger.info(f"Downloading file: {file_url}")

        file_req = requests.get(file_url, proxies=self.telegram_utils.get_proxies())
        file_req.raise_for_status()

        return file_req.content

    def remove_chat_from_known_chats(self, chat_id):
        self._logger.info(f"Removing chat {chat_id} from known chats")

        try:
            chat_picture_path = os.path.join(self.get_plugin_data_folder(), "img", "user", f"pic{int(chat_id)}.jpg")
            os.remove(chat_picture_path)
        except OSError:
            pass

        self._settings.remove(["chats", chat_id])
        self._settings.save()

        self._plugin_manager.send_plugin_message(
            self._identifier, {"type": "update_known_chats", "chats": self._settings.get(["chats"])}
        )

    def add_chat_to_known_chats(self, chat_id, chat_title, chat_type):
        self._logger.info(f"Adding new chat {chat_id} to known chats")

        new_chat_settings = copy.deepcopy(self.new_chat_settings)
        new_chat_settings["type"] = chat_type
        new_chat_settings["title"] = chat_title
        new_chat_settings["image"] = self.save_chat_picture(chat_id)

        settings_chats = self._settings.get(["chats"])
        settings_chats[chat_id] = new_chat_settings
        self._settings.set(["chats"], settings_chats)
        self._settings.save()

        self._plugin_manager.send_plugin_message(
            self._identifier, {"type": "update_known_chats", "chats": self._settings.get(["chats"])}
        )

        self.send_msg(
            f"{get_emoji('info')} Chat added to known chats. "
            "Before you can do anything, please go to plugin settings and edit your permissions.",
            chatID=chat_id,
        )

    def save_chat_picture(self, chat_id):
        if not self.bot_ready:
            return ""

        chat_id = int(chat_id)

        self._logger.debug(f"Saving chat picture for chat {chat_id}")

        try:
            is_group = is_group_or_channel(chat_id)

            output_dir = os.path.join(self.get_plugin_data_folder(), "img", "user")
            output_filename = os.path.join(output_dir, f"pic{chat_id}.jpg")
            os.makedirs(output_dir, exist_ok=True)

            file_id = None
            if is_group:
                json_data = self.telegram_utils.send_telegram_request(
                    f"{self.bot_url}/getChat",
                    "get",
                    params={"chat_id": chat_id},
                )
                file_id = json_data.get("result", {}).get("photo", {}).get("small_file_id")
            else:
                json_data = self.telegram_utils.send_telegram_request(
                    f"{self.bot_url}/getUserProfilePhotos",
                    "get",
                    params={"limit": 1, "user_id": chat_id},
                )
                photos = json_data.get("result", {}).get("photos", [])
                if photos and photos[0]:
                    file_id = photos[0][0].get("file_id")

            if not file_id:
                self._logger.debug(f"Chat {chat_id} has no photo")

                try:
                    os.remove(output_filename)
                except Exception:
                    pass

                return ""

            img_bytes = self.get_file(file_id)
            with Image.open(io.BytesIO(img_bytes)) as img:
                img = img.resize((40, 40), Image.LANCZOS)
                img.save(output_filename, format="JPEG")

            self._logger.info(f"Saved chat picture for chat id {chat_id}")

            # Nocache is used to force image refresh in the known chats table
            nocache = int(time.time())

            return f"/plugin/telegram/img/user/pic{chat_id}.jpg?nocache={nocache}"
        except Exception:
            self._logger.exception(f"Caught an exception saving chat picture for chat_id {chat_id}")
            return ""

    @contextmanager
    def telegram_action_context(self, chat_id, action):
        if not chat_id or not action:
            yield
            return

        stop_event = threading.Event()

        def _loop():
            try:
                while not stop_event.is_set():
                    self.telegram_utils.send_telegram_request(
                        f"{self.bot_url}/sendChatAction",
                        "get",
                        params={"chat_id": chat_id, "action": action},
                        timeout=5,
                    )
                    time.sleep(4.5)  # Telegram action expires after ~5s
            except Exception:
                self._logger.exception("Exception in telegram_action_context loop")

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()

        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=2)

    def test_token(self, token):
        # This will raise an exception if token is invalid
        json_data = self.telegram_utils.send_telegram_request(
            f"https://api.telegram.org/bot{token}/getMe",
            "get",
        )
        return f"@{json_data['result']['username']}"

    # Sets bot own list of commands
    def set_bot_commands(self):
        if not self.bot_ready:
            return

        commands = []
        for cmd_name, cmd_info in self.commands.commands_dict.items():
            if cmd_name.startswith("/"):
                commands.append(
                    {"command": cmd_name.lstrip("/"), "description": cmd_info.get("desc", "No description provided")}
                )

        self.telegram_utils.send_telegram_request(
            f"{self.bot_url}/setMyCommands",
            "post",
            data={"commands": json.dumps(commands)},
        )

    ##########
    ### Helper methods
    ##########

    # Check if the received command is allowed to be executed by the user
    def is_command_allowed(self, chat_id, from_id, command):
        # If no commands, nothing to allow
        if not command:
            return False

        chat_settings = self._settings.get(["chats", chat_id]) or {}
        chat_accept_commands = chat_settings.get("accept_commands", False)
        chat_accept_this_command = chat_settings.get("commands", {}).get(command, False)
        chat_allow_commands_from_users = chat_settings.get("allow_users", False)

        from_settings = self._settings.get(["chats", from_id]) or {}
        from_accept_commands = from_settings.get("accept_commands", False)
        from_accept_this_command = from_settings.get("commands", {}).get(command, False)

        # Always allowed commands (e.g., /help, etc)
        if "bind_none" in self.commands.commands_dict.get(command, {}):
            return True

        # Commands allowed for all chat members (both in private chat and in groups)
        if chat_accept_commands and chat_accept_this_command:
            return True

        # User personal permissions within groups
        if is_group_or_channel(chat_id) and chat_allow_commands_from_users:
            if from_accept_commands and from_accept_this_command:
                return True

        return False

    def pre_image(self):
        method = self._settings.get(["PreImgMethod"])

        if method == "None":
            return

        if method not in {"EVENT", "GCODE", "SYSTEM"}:
            self._logger.warning(f"Unknown pre_image method: {method}")
            return

        command = self._settings.get(["PreImgCommand"])
        delay = self._settings.get_int(["PreImgDelay"], min=0)

        self._logger.debug(f"Executing pre_image: method={method}, command={command}, delay={delay}s")

        if method == "EVENT":
            self._event_bus.fire("plugin_telegram_preimg")
        elif method == "GCODE":
            self._printer.commands(command)
            self._logger.debug("Pre_image gcode command sent")
        elif method == "SYSTEM":
            try:
                proc = subprocess.Popen(command, shell=True)
                self._logger.debug(f"Pre_image SYSTEM command started (PID={proc.pid})")
                proc.wait()
                self._logger.debug(f"Pre_image SYSTEM command finished with return code {proc.returncode}")
            except Exception:
                self._logger.exception(f"Caught an exception running pre_image SYSTEM command '{command}'")

        if delay:
            self._logger.debug(f"Pre_image: sleeping for {delay}s")
            time.sleep(delay)

    def post_image(self):
        method = self._settings.get(["PostImgMethod"])

        if method == "None":
            return

        if method not in {"EVENT", "GCODE", "SYSTEM"}:
            self._logger.warning(f"Unknown post_image method: {method}")
            return

        command = self._settings.get(["PostImgCommand"])
        delay = self._settings.get_int(["PostImgDelay"], min=0)

        self._logger.debug(f"Executing post_image: method={method}, command={command}, delay={delay}s")

        if delay:
            self._logger.debug(f"Post_image: sleeping for {delay}s")
            time.sleep(delay)

        if method == "EVENT":
            self._event_bus.fire("plugin_telegram_postimg")
        elif method == "GCODE":
            self._printer.commands(command)
            self._logger.debug("Post_image gcode command sent")
        elif method == "SYSTEM":
            try:
                proc = subprocess.Popen(command, shell=True)
                self._logger.debug(f"Post_image SYSTEM command started (PID={proc.pid})")
                proc.wait()
                self._logger.debug(f"Post_image SYSTEM command finished with return code {proc.returncode}")
            except Exception:
                self._logger.exception(f"Caught an exception running post_image SYSTEM command '{command}'")

    def get_webcam_profiles(self) -> List[WebcamProfile]:
        webcam_profiles: List[WebcamProfile] = []

        # New webcam integration (OctoPrint >= 1.9.0)
        try:
            if hasattr(octoprint.plugin.types, "WebcamProviderPlugin"):
                self._logger.debug("Getting webcam profiles from new webcam integration")

                webcam_providers = self._plugin_manager.get_implementations(octoprint.plugin.types.WebcamProviderPlugin)

                for provider in webcam_providers:
                    webcam_configurations = provider.get_webcam_configurations()
                    for wc in webcam_configurations:
                        compat = getattr(wc, "compat", None)
                        if not compat:
                            self._logger.debug("Skipped a webcam configuration without compatibility layer")
                            continue

                        webcam_profile = WebcamProfile(
                            name=getattr(wc, "name", None),
                            snapshot=getattr(compat, "snapshot", None),
                            snapshotTimeout=max(15, getattr(compat, "snapshotTimeout", 0)),
                            stream=getattr(compat, "stream", None),
                            flipH=bool(getattr(wc, "flipH", False)),
                            flipV=bool(getattr(wc, "flipV", False)),
                            rotate90=bool(getattr(wc, "rotate90", False)),
                        )

                        webcam_profiles.append(webcam_profile)
        except Exception:
            self._logger.exception("Caught exception getting new webcam integration profiles")

        # Fallback to Multicam plugin
        if not webcam_profiles:
            self._logger.warning("No webcams found via the new integration, falling back to Multicam plugin")

            try:
                if self._plugin_manager.get_plugin("multicam", True):
                    multicam_profiles = self._settings.global_get(["plugins", "multicam", "multicam_profiles"]) or []
                    self._logger.debug(f"Multicam profiles: {multicam_profiles}")

                    for multicam_profile in multicam_profiles:
                        webcam_profile = WebcamProfile(
                            name=multicam_profile.get("name"),
                            snapshot=multicam_profile.get("snapshot"),
                            snapshotTimeout=15,  # Multicam currently doesn't expose snapshotTimeout, see https://github.com/mikedmor/OctoPrint_MultiCam/issues/78
                            stream=multicam_profile.get("URL"),
                            flipH=bool(multicam_profile.get("flipH", False)),
                            flipV=bool(multicam_profile.get("flipV", False)),
                            rotate90=bool(multicam_profile.get("rotate90", False)),
                        )
                        webcam_profiles.append(webcam_profile)
                else:
                    self._logger.warning("Multicam not installed or disabled")
            except Exception:
                self._logger.exception("Caught exception getting Multicam profiles")

        # Fallback to legacy webcam settings
        if not webcam_profiles:
            self._logger.warning("No webcams found via Multicam, falling back to legacy webcam settings")

            try:
                webcam_profile = WebcamProfile(
                    name=self._settings.global_get(["webcam", "name"]),
                    snapshot=self._settings.global_get(["webcam", "snapshot"]),
                    snapshotTimeout=max(15, self._settings.global_get(["webcam", "snapshotTimeout"]) or 0),
                    stream=self._settings.global_get(["webcam", "stream"]),
                    flipH=bool(self._settings.global_get(["webcam", "flipH"])),
                    flipV=bool(self._settings.global_get(["webcam", "flipV"])),
                    rotate90=bool(self._settings.global_get(["webcam", "rotate90"])),
                )
                webcam_profiles.append(webcam_profile)
            except Exception:
                self._logger.exception("Caught exception getting legacy webcam settings")

        self._logger.debug(f"Final webcam profiles: {[p.__dict__ for p in webcam_profiles]}")

        return webcam_profiles

    def take_all_images(self) -> List[bytes]:
        taken_images_contents = []

        self._logger.debug("Taking all images")

        webcam_profiles = self.get_webcam_profiles()
        for webcam_profile in webcam_profiles:
            try:
                if not webcam_profile.snapshot:
                    self._logger.debug("Skipped a webcam without snapshot url")
                    continue

                taken_image_content = self.take_image(
                    webcam_profile.snapshot,
                    webcam_profile.flipH,
                    webcam_profile.flipV,
                    webcam_profile.rotate90,
                    webcam_profile.snapshotTimeout,
                )
                taken_images_contents.append(taken_image_content)
            except Exception:
                self._logger.exception("Caught an exception taking an image")

        return taken_images_contents

    def take_image(self, snapshot_url, flipH=False, flipV=False, rotate=False, timeout=15) -> bytes:
        snapshot_url = urljoin("http://localhost/", snapshot_url)

        self._logger.debug(f"Taking image from url: {snapshot_url}")

        r = requests.get(snapshot_url, timeout=timeout, verify=False)
        r.raise_for_status()

        image_content = r.content

        with io.BytesIO(image_content) as image_buffer:
            with Image.open(image_buffer) as image:
                image.load()

                if any([flipH, flipV, rotate]):
                    self._logger.debug(f"Applying image transformations: flipH={flipH}, flipV={flipV}, rotate={rotate}")

                    if flipH:
                        image = image.transpose(Image.FLIP_LEFT_RIGHT)
                    if flipV:
                        image = image.transpose(Image.FLIP_TOP_BOTTOM)
                    if rotate:
                        image = image.transpose(Image.ROTATE_90)

                with io.BytesIO() as output:
                    image.save(output, format="JPEG")
                    return output.getvalue()

    def take_all_gifs(self, duration=5) -> List[str]:
        taken_gif_paths = []

        self._logger.debug("Taking all gifs")

        webcam_profiles = self.get_webcam_profiles()
        for webcam_profile in webcam_profiles:
            try:
                if not webcam_profile.stream:
                    self._logger.debug("Skipped a webcam without stream url")
                    continue

                profile_name = webcam_profile.name or "default"
                gif_filename = secure_filename(f"gif_{profile_name}.mp4")

                taken_gif_path = self.take_gif(
                    webcam_profile.stream,
                    duration,
                    gif_filename,
                    webcam_profile.flipH,
                    webcam_profile.flipV,
                    webcam_profile.rotate90,
                )
                taken_gif_paths.append(taken_gif_path)
            except Exception:
                self._logger.exception("Caught an exception taking a gif")

        return taken_gif_paths

    def take_gif(
        self,
        stream_url,
        duration=5,
        gif_filename="gif.mp4",
        flipH=False,
        flipV=False,
        rotate=False,
    ) -> str:
        stream_url = urljoin("http://localhost/", stream_url)

        self._logger.debug(f"Taking gif from url: {stream_url}")

        gif_path = os.path.join(self.get_tmpgif_dir(), gif_filename)

        self._logger.debug(f"Removing file {gif_path}")
        try:
            os.remove(gif_path)
        except FileNotFoundError:
            pass

        settings_ffmpeg = self._settings.global_get(["webcam", "ffmpeg"])
        ffmpeg_path = (
            settings_ffmpeg
            if isinstance(settings_ffmpeg, str)
            and os.path.isfile(settings_ffmpeg)
            and os.access(settings_ffmpeg, os.X_OK)
            else shutil.which("ffmpeg")
        )
        if not ffmpeg_path:
            self._logger.error("ffmpeg not installed")
            raise RuntimeError("ffmpeg not installed")

        cpulimiter_path = shutil.which("cpulimit") or shutil.which("limitcpu")
        cpulimiter_disabled = self._settings.get(["no_cpulimit"]) or False
        if cpulimiter_disabled:
            self._logger.debug("CPU limiter disabled via settings")
        elif cpulimiter_path:
            self._logger.debug(f"Using CPU limiter: {cpulimiter_path}")
        else:
            self._logger.error("Neither cpulimit nor limitcpu is installed")
            raise RuntimeError("No CPU limiter (cpulimit or limitcpu) available")

        duration = max(1, min(duration, 60))
        self._logger.debug(f"duration={duration}")

        time_sec = str(timedelta(seconds=duration))
        self._logger.debug(f"timeSec={time_sec}")

        used_cpu, limit_cpu = 1, 65
        try:
            nb_cpu = multiprocessing.cpu_count()
            if nb_cpu > 1:
                used_cpu = nb_cpu // 2
                limit_cpu = 65 * used_cpu
            self._logger.debug(f"limit_cpu={limit_cpu} | used_cpu={used_cpu} | because nb_cpu={nb_cpu}")
        except Exception:
            self._logger.exception("Caught an exception getting number of cpu. Using defaults...")

        valid_presets = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        preset_setting = self._settings.get(["ffmpeg_preset"])
        preset = preset_setting if preset_setting in valid_presets else "medium"

        cmd = []
        if shutil.which("nice"):
            cmd = ["nice", "-n", "20"]

        if not cpulimiter_disabled:
            cmd += [
                cpulimiter_path,
                "-l",
                str(limit_cpu),
                "-f",
                "-z",
                "--",
            ]

        cmd += [
            ffmpeg_path,
            # Overwrite output file
            "-y",
            # Limit threads
            "-threads", str(used_cpu),
            # Video source
            "-i", str(stream_url),
            # Duration
            "-t", str(time_sec),
            # Video encoding
            "-color_range", "tv",
            "-c:v", "libx264",
            "-preset", preset,
            "-profile:v", "baseline",
            # Audio encoding
            "-c:a", "aac",
            "-ac", "2",
            # Enable fast start for streaming
            "-movflags", "+faststart",
        ]  # fmt: skip

        filters = ["format=yuv420p"]

        if flipV:
            filters.append("vflip")
        if flipH:
            filters.append("hflip")
        if rotate:
            filters.append("transpose=2")

        filter_str = ",".join(filters)
        cmd += ["-vf", filter_str]

        cmd.append(gif_path)

        self._logger.debug(f"Creating video by running command {cmd}")
        subprocess.run(cmd, check=True)
        self._logger.debug("Video created")

        if not os.path.isfile(gif_path):
            raise FileNotFoundError(f"Expected gif file was not created: {gif_path}")

        return gif_path

    def get_layer_progress_values(self):
        layer_progress_values = None

        try:
            displaylayerprogress_plugin_id = "DisplayLayerProgress"
            if self._plugin_manager.get_plugin(displaylayerprogress_plugin_id, True):
                values_request = self.send_octoprint_request(
                    f"/plugin/{displaylayerprogress_plugin_id}/values", timeout=3
                )
                layer_progress_values = values_request.json()
            else:
                self._logger.debug("DisplayLayerProgress plugin not installed or disabled")
        except Exception:
            self._logger.exception("Caught an exception in get_layer_progress_values")

        return layer_progress_values

    def calculate_ETA(self, printTime):
        current_time = datetime.now()
        finish_time = current_time + timedelta(seconds=printTime)

        if finish_time.day > current_time.day and finish_time > current_time + timedelta(days=7):
            # Longer than a week ahead
            format = self._settings.get(["WeekTimeFormat"])  # "%d.%m.%Y %H:%M:%S"
        elif finish_time.day > current_time.day:
            # Not today but within a week
            format = self._settings.get(["DayTimeFormat"])  # "%a %H:%M:%S"
        else:
            # Today
            format = self._settings.get(["TimeFormat"])  # "%H:%M:%S"

        return finish_time.strftime(format)

    def route_hook(self, server_routes, *args, **kwargs):
        from octoprint.server import app
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
                },
            ),
        ]

    def hook_gcode_sent(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        try:
            if gcode and gcode == "M600":
                self.on_event("gCode_M600", {})
        except Exception:
            self._logger.exception("Caught an exception on hook_gcode_sent")

    def hook_gcode_received(self, comm_instance, line, *args, **kwargs):
        try:
            if line.startswith("echo:busy: paused for user") or line.startswith("// action:paused"):
                if not self.user_pause_already_notified:
                    self.on_event("PausedForUser", {})
                    self.user_pause_already_notified = True
            elif line.startswith("echo:UserNotif"):
                self.on_event("UserNotif", {"UserNotif": line[15:]})
            elif line.startswith("ok"):
                self.user_pause_already_notified = False
        except Exception:
            self._logger.exception("Caught an exception on hook_gcode_received")

        return line

    def send_octoprint_simpleapi_command(self, plugin_id: str, command: str, parameters: dict = None, timeout: int = 5):
        """
        Sends a SimpleAPI command to an OctoPrint plugin via the HTTP API.

        Args:
            plugin_id (str): The ID of the plugin to target.
            command (str): The command string to send to the plugin.
            parameters (dict, optional): Additional parameters to include in the request body.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 5.

        Returns:
            requests.Response: The response object from the POST request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        payload = {"command": command}
        if parameters:
            payload.update(parameters)

        return self.send_octoprint_request(
            f"/api/plugin/{plugin_id}",
            "POST",
            headers={
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )

    def send_octoprint_simpleapi_get(self, plugin_id: str, parameters: dict = None, timeout: int = 5):
        """
        Sends a SimpleAPI GET request to an OctoPrint plugin via the HTTP API.

        Args:
            plugin_id (str): The ID of the plugin to target.
            parameters (dict, optional): Query parameters to include in the request.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 5.

        Returns:
            requests.Response: The response object from the GET request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        return self.send_octoprint_request(
            f"/api/plugin/{plugin_id}",
            params=parameters or {},
            timeout=timeout,
        )

    def send_octoprint_request(self, url: str, method: str = "GET", **kwargs):
        """
        Sends an HTTP request to the OctoPrint API with default authentication headers.

        Args:
            url (str): Full or relative URL (e.g., "/api/plugin/...").
            method (str): The HTTP method to use (e.g., "GET", "POST", "PUT", "PATCH", "DELETE", ...). Defaults to "GET".
            **kwargs: Additional arguments passed to the underlying requests library (e.g., 'data', 'params', 'files').

        Returns:
            requests.Response: The response object from the HTTP request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        url = urljoin(f"http://localhost:{self.port}/", url)

        method = method.lower()

        api_key = self._settings.global_get(["api", "key"])
        if not api_key:
            self._logger.error(
                "Global API Key not enabled. Most integrations with third-party plugins require enabling the Global API Key in OctoPrint Settings -> API -> Global API Key."
            )

        default_headers = {
            "X-Api-Key": api_key,
        }
        headers = {**default_headers, **(kwargs.get("headers") or {})}
        kwargs.pop("headers", None)

        default_kwargs = {
            "headers": headers,
            "timeout": 5,
        }
        request_kwargs = {**default_kwargs, **kwargs}

        loggable_kwargs = {}
        for k, v in request_kwargs.items():
            if k == "headers" and "X-Api-Key" in v:
                loggable_kwargs[k] = {**v, "X-Api-Key": "REDACTED"}
            elif k == "files":
                loggable_kwargs[k] = "<binary data>"
            else:
                loggable_kwargs[k] = v
        self._logger.debug(f"Sending OctoPrint request: method={method}, url={url}, kwargs={loggable_kwargs}.")

        response = requests.request(method, url, **request_kwargs)

        # Check if response content should be logged
        content_type = response.headers.get("content-type", "").lower()
        content_length = len(response.content)
        textual_content_types = [
            "application/json",
            "text/plain",
            "text/html",
            "text/xml",
            "application/xml",
            "text/javascript",
            "application/javascript",
        ]
        is_textual = any(ct in content_type for ct in textual_content_types)
        is_reasonable_size = content_length < 10 * 1024  # 10KB limit
        if is_textual and is_reasonable_size:
            self._logger.debug(f"Received OctoPrint response: status={response.status_code}, text={response.text}")
        else:
            self._logger.debug(
                f"Received OctoPrint response: status={response.status_code}, "
                f"content-type={content_type}, size={content_length} bytes"
            )

        response.raise_for_status()
        return response


# Check that we are running on OctoPrint >= 1.4.0, which introduced the granular permissions system
def get_implementation_class():
    if not is_octoprint_compatible(">=1.4.0"):
        raise Exception("OctoPrint 1.4.0 or greater required.")

    return TelegramPlugin()


__plugin_name__ = "Telegram"
__plugin_pythoncompat__ = ">=3.6,<4"
__plugin_privacypolicy__ = "https://github.com/jacopotediosi/OctoPrint-Telegram/blob/master/PRIVACY.md"
__plugin_implementation__ = get_implementation_class()
__plugin_hooks__ = {
    "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    "octoprint.server.http.routes": __plugin_implementation__.route_hook,
    "octoprint.comm.protocol.gcode.received": __plugin_implementation__.hook_gcode_received,
    "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.hook_gcode_sent,
    "octoprint.events.register_custom_events": __plugin_implementation__.register_custom_events,
}
