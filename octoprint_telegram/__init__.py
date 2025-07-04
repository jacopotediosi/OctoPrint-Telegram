import datetime
import io
import json
import logging
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from contextlib import contextmanager
from typing import List, Optional
from urllib.parse import urljoin

import octoprint.filemanager
import octoprint.plugin
import requests
import urllib3
from flask import jsonify
from flask_login import current_user
from octoprint.access.permissions import Permissions
from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
from octoprint.server import app
from octoprint.util.version import is_octoprint_compatible
from PIL import Image
from werkzeug.utils import secure_filename

from .emoji.emoji import Emoji
from .telegram_commands import TCMD
from .telegram_notifications import (
    TMSG,
    telegramMsgDict,
)  # Dict of known notification messages
from .telegram_utils import TelegramUtils, is_group_or_channel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

get_emoji = Emoji.get_emoji
bytes_reader_class = io.BytesIO


####################################################
#        TelegramListener Thread Class
# Connects to Telegram and will listen for messages.
# On incoming message the listener will process it.
####################################################


class TelegramListener(threading.Thread):
    def __init__(self, main):
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
        # Repeat fetching and processing messages until thread stopped
        self._logger.debug("Listener is running.")

        while not self.do_stop:
            try:
                self.loop()
            except Exception:
                self._logger.exception("Caught and exception running the listener loop.")

        self._logger.debug("Listener exits NOW.")

    # Try to get first contact. Repeat every 120sek if no success or stop if task stopped.
    def try_first_contact(self):
        got_contact = False
        while not self.do_stop and not got_contact:
            try:
                self.username = self.main.test_token()
                got_contact = True
                self.set_status(f"Connected as {self.username}", ok=True)
            except Exception as e:
                error_message = (
                    f"Caught an exception connecting to telegram: {e}. Waiting 2 minutes before trying again."
                )

                self._logger.exception(error_message)
                self.set_status(error_message)

                time.sleep(120)

    def loop(self):
        # Try to check for incoming messages. Wait 120 seconds and repeat on failure.
        try:
            updates = self.get_updates()
        except Exception as e:
            error_message = f"Caught an exception getting updates: {e}. Waiting 2 minutes before trying again."

            self._logger.exception(error_message)
            self.set_status(error_message)

            time.sleep(120)
            return

        for message in updates:
            try:
                self.process_message(message)
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

    def process_message(self, message):
        self._logger.debug(f"Processing message: {message}")

        self.set_update_offset(message["update_id"])

        if "message" in message and message["message"].get("chat"):
            self.main.chats = self.main._settings.get(["chats"])

            chat_id = self.get_chat_id(message)
            from_id = self.get_from_id(message)

            is_known_chat = chat_id in self.main.chats
            is_known_user = from_id in self.main.chats

            chat = message["message"]["chat"]

            data = self.main.chats.get(chat_id, dict(self.main.new_chat))

            data["type"] = chat["type"]

            if chat["type"] in ("group", "supergroup"):
                data["private"] = False
                data["title"] = chat["title"]
            elif chat["type"] == "private":
                data["private"] = True
                title_parts = []
                if "first_name" in chat:
                    title_parts.append(chat["first_name"])
                if "last_name" in chat:
                    title_parts.append(chat["last_name"])
                if "username" in chat:
                    title_parts.append(f"@{chat['username']}")
                data["title"] = " - ".join(title_parts)

            allow_users = data["allow_users"]
            accept_commands = data["accept_commands"]

            if not data["private"] and is_known_chat:
                if allow_users and not is_known_user and not accept_commands:
                    self._logger.warning("Previous command was from an unknown user.")
                    self.main.send_msg(
                        f"{get_emoji('notallowed')} I don't know you!",
                        chatID=chat_id,
                    )
                    return

            if not is_known_chat:
                self.main.chats[chat_id] = data

                self._logger.info(f"Got new chat: {chat_id}")

                self.main.send_msg(
                    f"{get_emoji('info')} Now I know you. "
                    "Before you can do anything, go to plugin settings and edit your permissions.",
                    chatID=chat_id,
                )

                try:
                    t = threading.Thread(target=self.main.save_chat_picture, kwargs={"chat_id": chat_id})
                    t.daemon = True
                    t.run()
                except Exception:
                    self._logger.exception(f"Caught an exception saving chat picture for chat_id {chat_id}")

                return

            # If message is a text message, we probably got a command.
            # When the command is not known, the following handler will discard it.
            if "text" in message["message"]:
                self.handle_text_message(message, chat_id, from_id)
            # We got no message with text (command) so lets check if we got a file.
            # The following handler will check file and saves it to disk.
            elif "document" in message["message"]:
                self.handle_document_message(message)
            # We got message with notification for a new chat title photo so lets download it
            elif "new_chat_photo" in message["message"]:
                self.handle_new_chat_photo_message(message)
            # We got message with notification for a deleted chat title photo so we do the same
            elif "delete_chat_photo" in message["message"]:
                self.handle_delete_chat_photo_message(message)
            # A member was removed from a group, so lets check if it's our bot and
            # delete the group from our chats if it is
            elif "left_chat_member" in message["message"]:
                self.handle_left_chat_member_message(message)
            # At this point we don't know what message type it is, so we do nothing
            else:
                self._logger.warning(f"Got an unknown message. Doing nothing. Data: {message}")
        elif "callback_query" in message:
            chat_id = self.get_chat_id(message)
            from_id = self.get_from_id(message)
            self.handle_callback_query(message, chat_id, from_id)
        else:
            self._logger.warning(
                "Message is missing .message or .message.chat or .message.callback_query. Skipping it."
            )

    def handle_callback_query(self, message, chat_id, from_id):
        message["callback_query"]["message"]["text"] = message["callback_query"]["data"]
        self.handle_text_message(message["callback_query"], chat_id, from_id)

    def handle_left_chat_member_message(self, message):
        self._logger.debug("Message Del_Chat")
        if (
            message["message"]["left_chat_member"]["username"] == self.username[1:]
            and str(message["message"]["chat"]["id"]) in self.main.chats
        ):
            del self.main.chats[str(message["message"]["chat"]["id"])]
            # Do a self._settings.save() ???
            self._logger.debug("Chat deleted")

    def handle_delete_chat_photo_message(self, message):
        chat_id = self.get_chat_id(message)

        self._logger.info(f"Chat {chat_id} deleted picture, deleting it...")

        path_to_remove = os.path.join(
            self.main.get_plugin_data_folder(),
            "img",
            "user",
            os.path.basename(f"pic{chat_id}.jpg"),
        )
        self._logger.info(f"Removing file {path_to_remove}")
        try:
            os.remove(path_to_remove)
        except OSError:
            self._logger.exception(f"Failed to remove file {path_to_remove}")

    def handle_new_chat_photo_message(self, message):
        chat_id = self.get_chat_id(message)

        # Only if we know the chat
        if chat_id in self.main.chats:
            self._logger.info(f"Chat {chat_id} changed picture, updating it...")

            try:
                t = threading.Thread(target=self.main.save_chat_picture, kwargs={"chat_id": chat_id})
                t.daemon = True
                t.run()
            except Exception:
                self._logger.exception(f"Caught an exception saving chat picture for chat_id {chat_id}")

    def handle_document_message(self, message):
        try:
            self._logger.debug("Handling document message")

            chat_id = self.get_chat_id(message)
            from_id = self.get_from_id(message)

            uploaded_file_filename = os.path.basename(message["message"]["document"]["file_name"])

            # Check if upload command is allowed
            if not self.main.is_command_allowed(chat_id, from_id, "/upload"):
                self._logger.warning(f"Received file {uploaded_file_filename} from an unauthorized user")
                self.main.send_msg(
                    f"{get_emoji('warning')} You are not authorized to upload files",
                    chatID=chat_id,
                )
                return

            # Check the file extension
            is_zip_file = False
            if not octoprint.filemanager.valid_file_type(uploaded_file_filename, "machinecode"):
                if uploaded_file_filename.lower().endswith(".zip"):
                    is_zip_file = True
                else:
                    self._logger.warning(f"Received file {uploaded_file_filename} with invalid extension")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Sorry, I only accept files with .gcode, .gco or .g or .zip extension",
                        chatID=chat_id,
                    )
                    return

            # Download the uploaded file
            self.main.send_msg(
                f"{get_emoji('save')} Saving file {uploaded_file_filename}...",
                chatID=chat_id,
            )
            uploaded_file_content = self.main.get_file(message["message"]["document"]["file_id"])

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

            # Prepare the response message
            if added_files_relative_paths:
                response_message = f"{get_emoji('download')} I've successfully saved the file(s) you sent me as {', '.join(added_files_relative_paths)}"
            else:
                response_message = f"{get_emoji('warning')} No files were added. Did you upload an empty zip?"

            # If there are multiple files or the "select file after upload" settings is off
            if len(added_files_relative_paths) != 1 or not self.main._settings.get(["selectFileUpload"]):
                # Just send the message
                self.main.send_msg(
                    response_message,
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )

            # If instead only one file has been added and the "select file after upload" settings is off
            else:
                # Check if printer is ready
                if not self.main._printer.is_ready():
                    response_message += " but I can't load it because the printer is not ready"
                    self.main.send_msg(
                        response_message,
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return

                # Load the uploaded file
                try:
                    file_to_select_abs_path = self.main._file_manager.path_on_disk(
                        octoprint.filemanager.FileDestinations.LOCAL,
                        added_files_relative_paths[0],
                    )
                    self._logger.debug(f"Selecting file: {file_to_select_abs_path}")
                    self.main._printer.select_file(file_to_select_abs_path, sd=False, printAfterSelect=False)
                except Exception:
                    response_message += " but I wasn't able to load the file"
                    self.main.send_msg(
                        response_message,
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return

                # Ask the user whether to print the loaded file
                response_message += (
                    f" and it is loaded.\n\n{get_emoji('question')} Do you want me to start printing it now?"
                )
                self.main.send_msg(
                    response_message,
                    noMarkup=True,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    responses=[
                        [
                            [
                                f"{get_emoji('check')} Print",
                                "/print_s",
                            ],
                            [
                                f"{get_emoji('cancel')} Cancel",
                                "/print_x",
                            ],
                        ]
                    ],
                    chatID=chat_id,
                )
        except Exception:
            self._logger.exception("Caught an exception processing a file")
            self.main.send_msg(
                (
                    f"{get_emoji('attention')} Something went wrong during processing of your file.\n"
                    f"Sorry. More details are in log files."
                ),
                chatID=chat_id,
            )

    def handle_text_message(self, message, chat_id, from_id):
        # We got a chat message.
        # Handle special messages from groups (/command@BotName).
        command = str(message["message"]["text"].split("@")[0])
        parameter = ""
        # TODO: Do we need this anymore?
        # reply_to_messages will be send on value inputs (eg notification height)
        # but also on android when pushing a button. Then we have to switch command and parameter.
        # if "reply_to_message" in message['message'] and "text" in message['message']['reply_to_message']:
        # command = message['message']['reply_to_message']['text']
        # parameter = message['message']['text']
        # if command not in [str(k) for k in self.main.tcmd.commandDict.keys()]:
        # command = message['message']['text']
        # parameter = message['message']['reply_to_message']['text']
        # if command is with parameter, get the parameter
        if any((f"{k}_") in command for k, v in self.main.tcmd.commandDict.items() if "param" in v):
            parameter = "_".join(command.split("_")[1:])
            command = command.split("_")[0]
        self._logger.info(
            f"Got a command: '{command}' with parameter: '{parameter}' in chat id {message['message']['chat']['id']}"
        )
        # Is command  known?
        if command not in self.main.tcmd.commandDict:
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
                sender = (
                    message.get("from")  # Callback query
                    or message.get("message", {}).get("from")  # Other messages
                    or {}
                )

                username = sender.get("username")

                first_name = sender.get("first_name")
                last_name = sender.get("last_name")
                fullname = " ".join(part for part in [first_name, last_name] if part).strip()

                parts = []

                if username:
                    parts.append(f"@{username}")
                if fullname:
                    parts.append(fullname)

                user += " - ".join(parts) if parts else "unknown"
            except Exception:
                user += "unknown"

            # Execute command
            self.main.tcmd.commandDict[command]["cmd"](chat_id, from_id, command, parameter, user)
        else:
            # User was not allowed to execute this command
            self._logger.warning("Previous command was from an unauthorized user.")
            self.main.send_msg(
                f"You are not allowed to do this! {get_emoji('notallowed')}",
                chatID=chat_id,
            )

    def get_chat_id(self, message):
        if "message" in message:
            chat = message["message"]["chat"]
        elif "callback_query" in message:
            chat = message["callback_query"]["message"]["chat"]
        else:
            raise ValueError("Unsupported message type: no 'message' or 'callback_query' found")

        chat_id = chat["id"]

        return str(chat_id)

    def get_from_id(self, message):
        if "message" in message:
            from_id = message["message"]["from"]["id"]
        elif "callback_query" in message:
            from_id = message["callback_query"]["from"]["id"]
        else:
            raise ValueError("Unsupported message type: no 'message' or 'callback_query' found")

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


class TelegramPluginLoggingFilter(logging.Filter):
    def filter(self, record):
        # Redact Telegram bot tokens from logs
        pattern = r"[0-9]{8,10}:[a-zA-Z0-9_-]{35}"
        msg = str(record.msg) if not isinstance(record.msg, str) else record.msg

        for match in re.findall(pattern, msg):
            record.msg = msg.replace(match, "REDACTED")
        return True


class WebcamProfile:
    def __init__(
        self,
        name: Optional[str] = None,
        snapshot: Optional[str] = None,
        stream: Optional[str] = None,
        flipH: bool = False,
        flipV: bool = False,
        rotate90: bool = False,
    ):
        self.name = name
        self.snapshot = snapshot
        self.stream = stream
        self.flipH = flipH
        self.flipV = flipV
        self.rotate90 = rotate90

    def __repr__(self):
        return (
            f"<WebcamProfile name={self.name!r} snapshot={self.snapshot!r} "
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
    def __init__(self):
        # For more init stuff see on_after_startup()
        self._logger = logging.getLogger("octoprint.plugins.telegram")
        self.thread = None
        self.bot_url = None
        self.chats = {}
        self.connection_state_str = "Disconnected."
        self.connection_ok = False
        self.port = 5000
        self.update_message_id = {}
        self.shut_up = {}
        self.send_messages = True
        self.telegram_utils = None
        self.tcmd = None
        self.tmsg = None
        self.sending_okay_minute = None
        self.sending_okay_count = 0
        # Initial settings for new chat. See on_after_startup()
        # !!! sync with new_usr_dict in on_settings_migrate() !!!
        self.new_chat = {}

    # Starts the telegram listener thread
    def start_listening(self):
        token = self._settings.get(["token"])
        if token != "" and self.thread is None:
            self._logger.debug("Starting listener.")
            self.bot_url = f"https://api.telegram.org/bot{token}"
            self.bot_file_url = f"https://api.telegram.org/file/bot{token}"
            self.thread = TelegramListener(self)
            self.thread.daemon = True
            self.thread.start()

    # Stops the telegram listener thread
    def stop_listening(self):
        if self.thread is not None:
            self._logger.debug("Stopping listener.")
            self.thread.stop()
            self.thread = None

    def shutdown(self):
        self._logger.warning("shutdown() running!")
        self.stop_listening()
        self.send_messages = False

    def sending_okay(self):
        # If the count ever goeas above 10, we stop doing everything else and just return False.
        # So if this is ever reached, it will stay this way.
        if self.sending_okay_count > 10:
            self._logger.warning("Sent more than 10 messages in the last minute. Shutting down...")
            self.shutdown()
            return False

        if self.sending_okay_minute != datetime.datetime.now().minute:
            self.sending_okay_minute = datetime.datetime.now().minute
            self.sending_okay_count = 1
        else:
            self.sending_okay_count += 1

        return True

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
        # Logging formatter
        logging_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # File logging handler
        file_handler = CleaningTimedRotatingFileHandler(
            self._settings.get_plugin_logfile_path(),
            when="D",
            backupCount=3,
        )
        file_handler.setFormatter(logging_formatter)
        file_handler.addFilter(TelegramPluginLoggingFilter())
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
        self.tcmd = TCMD(self)
        self.triggered = False

        # Notification Message Handler class. called only by on_event()
        self.tmsg = TMSG(self)

        # Initial settings for new chat.
        # !!! sync this dict with new_usr_dict in on_settings_migrate() !!!
        self.new_chat = {
            "private": True,
            "title": "[UNKNOWN]",
            "accept_commands": False,
            "send_notifications": False,
            "new": True,
            "type": "",
            "allow_users": False,
            "commands": {k: False for k, v in self.tcmd.commandDict.items()},
            "notifications": {k: False for k, v in telegramMsgDict.items()},
        }

        self.chats = self._settings.get(["chats"])

        # Create / clean tmpgif folder
        shutil.rmtree(self.get_tmpgif_dir(), ignore_errors=True)
        os.makedirs(self.get_tmpgif_dir(), exist_ok=True)

        self.start_listening()

        # Delete user profile photos if user doesn't exist anymore
        img_user_dir = os.path.join(self.get_plugin_data_folder(), "img", "user")
        for filename in os.listdir(img_user_dir):
            file_path = os.path.join(img_user_dir, filename)
            if os.path.isfile(file_path):
                filename_chat_id = filename.split(".")[0][3:]
                self._logger.debug(f"Testing Pic ID {filename_chat_id}")
                if filename_chat_id not in self.chats:
                    self._logger.debug(f"Removing file {file_path}")
                    try:
                        os.remove(file_path)
                    except OSError:
                        self._logger.exception(f"Caught an exception removing file {file_path}")

        # Update user profile photos
        for chat_id in self.chats:
            try:
                if chat_id != "zBOTTOMOFCHATS":
                    t = threading.Thread(target=self.save_chat_picture, kwargs={"chat_id": chat_id})
                    t.daemon = True
                    t.run()
            except Exception:
                self._logger.exception(f"Caught an exception saving chat picture for chat_id {chat_id}")

    def on_shutdown(self):
        self.on_event("PrinterShutdown", {})
        self.stop_listening()

    ##########
    ### Settings API
    ##########

    def get_settings_version(self):
        return 5
        # Settings version numbers used in releases
        # < 1.3.0: no settings versioning
        # 1.3.0 : 1
        # 1.3.1 : 2
        # 1.3.2 : 2
        # 1.3.3 : 2
        # 1.4.0 : 3
        # 1.4.1 : 3
        # 1.4.2 : 3
        # 1.4.3 : 4
        # 1.5.1 : 5 (PauseForUser)

    def get_settings_defaults(self):
        return dict(
            token="",
            notification_height=5.0,
            notification_time=15,
            message_at_print_done_delay=0,
            messages=telegramMsgDict,
            chats={
                "zBOTTOMOFCHATS": {
                    "send_notifications": False,
                    "accept_commands": False,
                    "private": False,
                }
            },
            debug=False,
            send_icon=True,
            image_not_connected=True,
            gif_not_connected=False,
            send_gif=False,
            no_mistake=False,
            fileOrder=False,
            ffmpeg_preset="medium",
            PreImgMethod="None",
            PreImgCommand="",
            PostImgMethod="None",
            PostImgCommand="",
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

    def on_settings_migrate(self, target, current=None):
        self._logger.setLevel(logging.DEBUG)
        self._logger.debug("MIGRATE DO")
        tcmd = TCMD(self)
        # Initial settings for new chat
        # !!! sync this dict with self.new_chat in on_after_startup() !!!
        new_usr_dict = {
            "private": True,
            "title": "[UNKNOWN]",
            "accept_commands": False,
            "send_notifications": False,
            "new": False,
            "type": "",
            "allow_users": False,
            "commands": {k: False for k, v in tcmd.commandDict.items()},
            "notifications": {k: False for k, v in telegramMsgDict.items()},
        }

        ##########
        ### Migrate from old plugin Versions < 1.3 (old versions had no settings version check)
        ##########
        chats = {k: v for k, v in self._settings.get(["chats"]).items() if k != "zBOTTOMOFCHATS"}
        self._logger.debug(f"LOADED CHATS: {chats}")
        self._settings.set(["chats"], {})
        if current is None or current < 1:
            ########## Update Chats
            # There shouldn't be any chats, but maybe someone had installed any test branch.
            # Then we have to check if all needed settings are populated.
            for chat in chats:
                for setting in new_usr_dict:
                    if setting not in chats[chat]:
                        if setting == "commands":
                            chats[chat]["commands"] = {
                                k: False for k, v in tcmd.commandDict.items() if "bind_none" not in v
                            }
                        elif setting == "notifications":
                            chats[chat]["notifications"] = {k: False for k, v in telegramMsgDict.items()}
                        else:
                            chats[chat][setting] = False
            ########## Is there a chat from old single user plugin version?
            # Then migrate it into chats.
            chat = self._settings.get(["chat"])
            if chat is not None:
                self._settings.set(["chat"], None)
                data = {}
                data.update(new_usr_dict)
                data["private"] = True
                data["title"] = "[UNKNOWN]"
                # Try to get infos from telegram by sending a "you are migrated" message
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
                        f"{self.main.bot_url}/sendMessage",
                        "post",
                        data=message,
                    )

                    chat = json_data["result"]["chat"]

                    if chat["type"] == "group" or chat["type"] == "supergroup":
                        data["private"] = False
                        data["title"] = chat["title"]
                    elif chat["type"] == "private":
                        data["private"] = True
                        title_parts = []
                        if "first_name" in chat:
                            title_parts.append(chat["first_name"])
                        if "last_name" in chat:
                            title_parts.append(chat["last_name"])
                        if "username" in chat:
                            title_parts.append(f"@{chat['username']}")
                        data["title"] = " - ".join(title_parts)

                except Exception:
                    self._logger.exception("ERROR migrating chat. Done with defaults private=true,title=[UNKNOWN]")

                # Place the migrated chat in chats
                chats.update({str(chat["id"]): data})

            self._logger.debug(f"MIGRATED Chats: {chats}")

            ########## Update messages. Old text will be taken to new structure.
            messages = self._settings.get(["messages"])
            msg_out = {}
            for msg in messages:
                if msg == "TelegramSendNotPrintingStatus":
                    msg2 = "StatusNotPrinting"
                elif msg == "TelegramSendPrintingStatus":
                    msg2 = "StatusPrinting"
                else:
                    msg2 = msg
                if type(messages[msg]) is not type({}):
                    new_msg = telegramMsgDict[msg2].copy()
                    new_msg["text"] = str(messages[msg])
                    msg_out.update({msg2: new_msg})
                else:
                    msg_out.update({msg2: messages[msg]})
            self._settings.set(["messages"], msg_out)
            ########## Delete old settings
            self._settings.set(["message_at_startup"], None)
            self._settings.set(["message_at_shutdown"], None)
            self._settings.set(["message_at_print_started"], None)
            self._settings.set(["message_at_print_done"], None)
            self._settings.set(["message_at_print_failed"], None)

        ##########
        ### Migrate to new command/notification settings version.
        ### This should work on all future versions. So if you add/del
        ### some commands/notifications, then increment settings version counter
        ### in get_settings_version(). This will trigger octoprint to update settings
        ##########
        if current is None or current < target:
            # First we have to check if anything has changed in commandDict or telegramMsgDict
            # then we have to update user command or notification settings

            # This for loop updates commands and notifications settings items of chats.
            # If there are changes in commandDict or telegramMsgDict.
            for chat in chats:
                # Handle renamed commands
                if "/list" in chats[chat]["commands"]:
                    chats[chat]["commands"].update({"/files": chats[chat]["commands"]["/list"]})
                if "/imsorrydontshutup" in chats[chat]["commands"]:
                    chats[chat]["commands"].update({"/dontshutup": chats[chat]["commands"]["/imsorrydontshutup"]})
                if "type" not in chats[chat]:
                    chats[chat].update({"type": "PRIVATE" if chats[chat]["private"] else "GROUP"})
                del_cmd = []
                # Collect remove 'bind_none' commands
                for cmd in tcmd.commandDict:
                    if cmd in chats[chat]["commands"] and "bind_none" in tcmd.commandDict[cmd]:
                        del_cmd.append(cmd)
                # Collect Delete commands from settings if they don't belong to commandDict anymore
                for cmd in chats[chat]["commands"]:
                    if cmd not in tcmd.commandDict:
                        del_cmd.append(cmd)
                # Finally delete commands
                for cmd in del_cmd:
                    del chats[chat]["commands"][cmd]
                # If there are new commands in commandDict, add them to settings
                for cmd in tcmd.commandDict:
                    if cmd not in chats[chat]["commands"]:
                        if "bind_none" not in tcmd.commandDict[cmd]:
                            chats[chat]["commands"].update({cmd: False})
                # Delete notifications from settings if they don't belong to msgDict anymore
                del_msg = []
                for msg in chats[chat]["notifications"]:
                    if msg not in telegramMsgDict:
                        del_msg.append(msg)
                for msg in del_msg:
                    del chats[chat]["notifications"][msg]
                # If there are new notifications in msgDict, add them to settings
                for msg in telegramMsgDict:
                    if msg not in chats[chat]["notifications"]:
                        chats[chat]["notifications"].update({msg: False})
            self._settings.set(["chats"], chats)

            ########## If anything changed in telegramMsgDict, we also have to update settings for messages
            messages = self._settings.get(["messages"])
            # This for loop deletes items from messages settings
            # if they don't belong to telegramMsgDict anymore
            del_msg = []
            for msg in messages:
                if msg not in telegramMsgDict:
                    del_msg.append(msg)
            for msg in del_msg:
                del messages[msg]
            # This for loop adds new message settings from telegramMsgDict to settings
            for msg in telegramMsgDict:
                if msg not in messages:
                    messages.update({msg: telegramMsgDict[msg]})

            self._settings.set(["messages"], messages)
            self._logger.debug(f"MESSAGES: {self._settings.get(['messages'])}")

        ##########
        ### Save the settings after Migration is done
        ##########
        self._logger.debug(f"SAVED Chats: {self._settings.get(['chats'])}")
        try:
            self._settings.save()
        except Exception:
            self._logger.exception("MIGRATED Save failed")
        self._logger.debug("MIGRATED Saved")

    def on_settings_save(self, data):
        # Remove 'new'-flag and apply bindings for all chats
        if data.get("chats"):
            del_list = []
            for key in data["chats"]:
                if "new" in data["chats"][key]:
                    data["chats"][key]["new"] = False
                # Look for deleted chats
                if key not in self.chats and not key == "zBOTTOMOFCHATS":
                    del_list.append(key)
            # Delete chats finally
            for key in del_list:
                del data["chats"][key]
        # Also remove 'new'-flag from self.chats so settingsUI is consistent
        # self.chats will only update to settings data on first received message after saving done
        for key in self.chats:
            if "new" in self.chats[key]:
                self.chats[key]["new"] = False

        self._logger.debug(f"Saving data: {data}")
        # Check token for right format
        if "token" in data:
            data["token"] = data["token"].strip()
            if not re.match(r"^[0-9]+:[a-zA-Z0-9_\-]+$", data["token"]):
                self._logger.error("Not saving token because it doesn't seem to have the right format.")
                self.connection_state_str = "The previously entered token doesn't seem to have the correct format. It should look like this: 12345678:AbCdEfGhIjKlMnOpZhGtDsrgkjkZTCHJKkzvjhb"
                data["token"] = ""
        old_token = self._settings.get(["token"])
        # Now save settings
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        # Reconnect on new token
        # Will stop listener on invalid token
        if "token" in data:
            if data["token"] != old_token:
                self.stop_listening()
            if data["token"] != "":
                self.start_listening()
            else:
                self.connection_state_str = "No token given."

    def on_settings_load(self):
        data = octoprint.plugin.SettingsPlugin.on_settings_load(self)

        # Only return our restricted settings to admin users - this is only needed for OctoPrint <= 1.2.16
        restricted = (("token", None), ("chats", dict()))
        for r, v in restricted:
            if r in data and (current_user is None or current_user.is_anonymous() or not current_user.is_admin()):
                data[r] = v

        return data

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
    ### EventHandler API
    ##########

    def on_event(self, event, payload, **kwargs):
        try:
            if not self.tmsg:
                self._logger.debug("Received an event, but tmsg is not initialized yet")
                return

            # If we know the event, start handler
            if event in self.tmsg.msgCmdDict:
                self._logger.debug(f"Received a known event: {event} - Payload: {payload}")
                self.tmsg.startEvent(event, payload, **kwargs)
        except Exception:
            self._logger.exception("Caught exception handling an event")

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

        return self.get_chat_settings("bindings" in request.args)

    def get_chat_settings(self, bindings=False):
        if bindings:
            bind_text = {}
            for key in {k: v for k, v in telegramMsgDict.items() if "bind_msg" in v}:
                if telegramMsgDict[key]["bind_msg"] in bind_text:
                    bind_text[telegramMsgDict[key]["bind_msg"]].append(key)
                else:
                    bind_text[telegramMsgDict[key]["bind_msg"]] = [key]
            return jsonify(
                {
                    "bind_cmd": [k for k, v in self.tcmd.commandDict.items() if "bind_none" not in v],
                    "bind_msg": [k for k, v in telegramMsgDict.items() if "bind_msg" not in v],
                    "bind_text": bind_text,
                    "no_setting": [k for k, v in telegramMsgDict.items() if "no_setting" in v],
                }
            )
        else:
            ret_chats = {k: v for k, v in self.chats.items() if "delMe" not in v and k != "zBOTTOMOFCHATS"}
            for chat_id in ret_chats:
                if os.path.isfile(
                    os.path.join(
                        self.get_plugin_data_folder(),
                        "img",
                        "user",
                        os.path.basename(f"pic{chat_id}.jpg"),
                    )
                ):
                    ret_chats[chat_id]["image"] = f"/plugin/telegram/img/user/pic{chat_id}.jpg"
                elif is_group_or_channel(chat_id):
                    ret_chats[chat_id]["image"] = "/plugin/telegram/static/img/group.jpg"
                else:
                    ret_chats[chat_id]["image"] = "/plugin/telegram/static/img/default.jpg"

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
            setCommandList=[],
            testEvent=["event"],
            testToken=["token"],
            editUser=[
                "chat_id",
                "accept_commands",
                "send_notifications",
                "allow_users",
            ],
        )

    def on_api_command(self, command, data):
        self._logger.info(f"Received API command {command} with data {data}")

        if not Permissions.SETTINGS.can():
            self._logger.warning("API command was not allowed")
            return "Insufficient permissions", 403

        if command == "testToken":
            token = str(data.get("token"))

            try:
                username = self.test_token(token)
                self._settings.set(["token"], token)
                self._settings.save()

                self._logger.info("Token set via testToken API command")

                # To start with new token if already running
                self.stop_listening()
                self.start_listening()

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

        # Delete a chat
        elif command == "delChat":
            chat_id = str(data.get("chat_id"))

            if chat_id not in self.chats:
                self._logger.warning(f"Chat id {chat_id} is unknown")
                return "Unknown chat with given id", 404

            self.chats.pop(chat_id)
            self._settings.set(["chats"], self.chats)
            self._settings.save()

            self._logger.info(f"Chat {chat_id} deleted")

            return jsonify(
                {
                    "chats": {k: v for k, v in self.chats.items() if "delMe" not in v and k != "zBOTTOMOFCHATS"},
                    "connection_state_str": self.connection_state_str,
                    "connection_ok": self.connection_ok,
                }
            )

        elif command == "testEvent":
            event = data.get("event")
            try:
                self.on_event(event, {})
                self._logger.info(f"Event {event} tested")
                return jsonify({"ok": True})
            except Exception as e:
                self._logger.exception(f"Caught an exception testing event {event}: {e}")
                return jsonify({"ok": False})

        elif command == "setCommandList":
            try:
                self.set_bot_commands()
                self._logger.info("Bot commands set")
                return jsonify(
                    {
                        "ok": True,
                        "setMyCommands_state_str": "Commands set",
                    }
                )
            except Exception as e:
                self._logger.exception("Caught an exception setting bot commands")
                return jsonify(
                    {
                        "ok": False,
                        "setMyCommands_state_str": f"Error setting commands: {e}",
                    }
                )

        elif command == "editUser":
            chat_id = str(data.get("chat_id"))

            # Check if chat_id is known
            if chat_id not in self.chats:
                self._logger.warning(f"Chat id {chat_id} is unknown")
                return "Unknown chat with given id", 404

            settings_keys = ("accept_commands", "send_notifications", "allow_users")

            # Check that settings_keys are boolean
            invalid_keys = [k for k in settings_keys if not isinstance(data.get(k), bool)]
            if invalid_keys:
                self._logger.warning(f"Received args {', '.join(invalid_keys)} are not boolean")
                return f"Invalid values: {', '.join(invalid_keys)} must be boolean", 400

            # Update user
            for key in settings_keys:
                self.chats[chat_id][key] = data[key]

            # Logging successful user update
            settings = ", ".join(f"{k}={data[k]}" for k in settings_keys)
            self._logger.info(f"Updated settings for chat {chat_id} - {settings}")

            # Return updated chats settings
            return self.get_chat_settings()

    ##########
    ### Telegram API-Functions
    ##########

    def send_msg(self, message, **kwargs):
        if not self.send_messages:
            return

        kwargs["message"] = message
        try:
            # If it's a regular event notification
            if "chatID" not in kwargs and "event" in kwargs:
                self._logger.debug(f"Send_msg() found event: {kwargs['event']} | chats list={self.chats}")
                for key in self.chats:
                    self._logger.debug(f"send_msg loop key = {key}")
                    if key != "zBOTTOMOFCHATS":
                        try:
                            self._logger.debug(f"self.chats[key]['notifications'] = {self.chats[key]['notifications']}")
                            if (
                                self.chats[key]["notifications"][kwargs["event"]]
                                and (key not in self.shut_up or self.shut_up[key] == 0)
                                and self.chats[key]["send_notifications"]
                            ):
                                kwargs["chatID"] = key
                                threading.Thread(target=self._send_msg, kwargs=kwargs).run()
                        except Exception:
                            self._logger.exception(f"Caught an exception in loop chatId for key: {key}")
            # Seems to be a broadcast
            elif "chatID" not in kwargs:
                for key in self.chats:
                    kwargs["chatID"] = key
                    threading.Thread(target=self._send_msg, kwargs=kwargs).run()
            # This is a 'editMessageText' message
            elif "msg_id" in kwargs and kwargs["msg_id"] != "" and kwargs["msg_id"] is not None:
                threading.Thread(target=self._send_edit_msg, kwargs=kwargs).run()
            # Direct message or event notification to a chat_id
            else:
                threading.Thread(target=self._send_msg, kwargs=kwargs).run()
        except Exception:
            self._logger.exception("Caught an exception in send_msg()")

    # This method is used to update a message text of a sent message.
    # The sent message had to have no_markup = true when calling send_msg() (otherwise it would not work)
    # by setting no_markup = true we got a messageg_id on sending the message which is saved in self.update_message_id.
    # If this message_id is passed in msg_id to send_msg() then this method will be called.
    def _send_edit_msg(
        self,
        message="",
        msg_id="",
        chatID="",
        responses=None,
        inline=True,
        markup="off",
        delay=0,
        **kwargs,
    ):
        if not self.send_messages:
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
            if responses and inline:
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

            if inline:
                self.update_message_id[chatID] = msg_id

        except Exception:
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
        inline=True,
        chatID="",
        markup="off",
        show_web=False,
        silent=False,
        gif_duration=5,
        **kwargs,
    ):
        self._logger.debug(f"Start _send_msg with args: {locals()}")

        try:
            # Check if messages are enabled
            if not self.send_messages:
                self._logger.debug("Not enabled to send messages, return...")
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

            # Pre image
            if with_image or with_gif:
                try:
                    self.pre_image()
                except Exception:
                    self._logger.exception("Caught an exception calling pre_image()")

            # Prepare images to send
            images_to_send = []

            # Add thumbnails to images to send
            if kwargs.get("thumbnail"):
                try:
                    self._logger.debug(f"Get thumbnail: {kwargs.get('thumbnail')}")

                    url = f"http://localhost:{self.port}/{kwargs.get('thumbnail', '')}"

                    thumbnail_response = requests.get(url)
                    thumbnail_response.raise_for_status()

                    images_to_send.append(thumbnail_response.content)
                except Exception:
                    self._logger.exception("Caught an exception getting thumbnail")

            # Add webcam images to images to send
            if with_image:
                with self.telegram_action_context(chatID, "record_video"):
                    try:
                        images_to_send += self.take_all_images()
                    except Exception:
                        self._logger.exception("Caught an exception taking all images")

            # Prepare gifs to send
            gifs_to_send = []

            # Add movie to gifs to send
            movie = kwargs.get("movie")
            if movie:
                gifs_to_send.append(movie)

            # Add gifs to gifs to send
            if with_gif:
                with self.telegram_action_context(chatID, "record_video"):
                    try:
                        gifs_to_send += self.take_all_gifs(gif_duration)
                    except Exception:
                        self._logger.exception("Caught an exception taking all gifs")

            # Post image
            if with_image or with_gif:
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

            # Inline handling
            if inline:
                if "message_id" in tlg_response["result"]:
                    self.update_message_id[chatID] = tlg_response["result"]["message_id"]

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

    def humanbytes(self, B):
        "Return the given bytes as a human friendly KB, MB, GB, or TB string"
        B = float(B)

        KB = float(1024)
        MB = float(KB**2)
        GB = float(KB**3)
        TB = float(KB**4)

        if B < KB:
            return f"{B} {'Bytes' if B != 1 else 'Byte'}"
        elif KB <= B < MB:
            return f"{B / KB:.2f} KB"
        elif MB <= B < GB:
            return f"{B / MB:.2f} MB"
        elif GB <= B < TB:
            return f"{B / GB:.2f} GB"
        elif TB <= B:
            return f"{B / TB:.2f} TB"

    def send_file(self, chat_id, path, text):
        if not self.send_messages:
            return

        with self.telegram_action_context(chat_id, "upload_document"):
            self._logger.info(f"Sending file {path} to chat {chat_id}")

            with open(path, "rb") as document:
                self.telegram_utils.send_telegram_request(
                    f"{self.bot_url}/sendDocument",
                    "post",
                    files={"document": document},
                    data={"chat_id": chat_id, "caption": text},
                )

    def get_file(self, file_id):
        if not self.send_messages:
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

    def save_chat_picture(self, chat_id):
        if not self.send_messages:
            return

        self._logger.debug(f"Saving chat picture for chat_id {chat_id}")

        if is_group_or_channel(chat_id):
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
            file_id = json_data.get("result", {}).get("photos", [])
            file_id = file_id[0][0].get("file_id") if file_id and file_id[0] else None

        if not file_id:
            self._logger.debug(f"Chat id {chat_id} has no photo.")
            return

        img_bytes = self.get_file(file_id)

        output_filename = os.path.join(
            self.get_plugin_data_folder(),
            "img",
            "user",
            os.path.basename(f"pic{chat_id}.jpg"),
        )

        img = Image.open(bytes_reader_class(img_bytes))
        img = img.resize((40, 40), Image.LANCZOS)
        img.save(output_filename, format="JPEG")

        self._logger.info(f"Saved chat picture for chat id {chat_id}")

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

    def test_token(self, token=None):
        if not self.send_messages:
            return

        if token is None:
            token = self._settings.get(["token"])

        json_data = self.telegram_utils.send_telegram_request(
            f"https://api.telegram.org/bot{token}/getMe",
            "get",
        )
        return f"@{json_data['result']['username']}"

    # Sets bot own list of commands
    def set_bot_commands(self):
        if not self.send_messages:
            return

        commands = [
            {
                "command": "status",
                "description": "Displays the current status including a capture from the camera",
            },
            {
                "command": "togglepause",
                "description": "Pauses/Resumes current print",
            },
            {
                "command": "home",
                "description": "Home the printer print head",
            },
            {
                "command": "files",
                "description": "Lists all the files available for printing",
            },
            {
                "command": "print",
                "description": "Lets you start a print (confirmation required)",
            },
            {
                "command": "tune",
                "description": "Sets feed and flow rate, control temperatures",
            },
            {
                "command": "ctrl",
                "description": "Activates self defined controls from Octoprint",
            },
            {
                "command": "con",
                "description": "Connects or disconnects the printer",
            },
            {
                "command": "sys",
                "description": "Executes Octoprint system commands",
            },
            {
                "command": "abort",
                "description": "Aborts the currently running print (confirmation required)",
            },
            {"command": "off", "description": "Turn off the printer"},
            {"command": "on", "description": "Turn on the printer"},
            {
                "command": "settings",
                "description": "Displays notification settings and lets change them",
            },
            {
                "command": "upload",
                "description": "Stores a file into the Octoprint library",
            },
            {
                "command": "filament",
                "description": "Shows filament spools and lets you change it (requires Filament Manager Plugin)",
            },
            {"command": "user", "description": "Gets user info"},
            {
                "command": "gcode",
                "description": "Call gCode commande with /gcode_XXX where XXX is the gcode command",
            },
            {
                "command": "gif",
                "description": "Sends a gif from the current video",
            },
            {
                "command": "supergif",
                "description": "Sends a bigger gif from the current video",
            },
            {
                "command": "photo",
                "description": "Sends photo from webcams",
            },
            {
                "command": "shutup",
                "description": "Disables automatic notifications until the next print ends",
            },
            {
                "command": "dontshutup",
                "description": "Makes the bot talk again (opposite of `/shutup`)",
            },
            {"command": "help", "description": "Shows this help message"},
        ]

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

        chat_settings = self.chats.get(chat_id, {})
        chat_accept_commands = chat_settings.get("accept_commands", False)
        chat_accept_this_command = chat_settings.get("commands", {}).get(command, False)
        chat_allow_commands_from_users = chat_settings.get("allow_users", False)

        from_settings = self.chats.get(from_id, {})
        from_accept_commands = from_settings.get("accept_commands", False)
        from_accept_this_command = from_settings.get("commands", {}).get(command, False)

        # Always allowed commands (e.g., /help, etc)
        if "bind_none" in self.tcmd.commandDict[command]:
            return True

        # Commands allowed for all chat members (both in private chat and in groups)
        if chat_accept_commands and chat_accept_this_command:
            return True

        # User personal permissions within groups
        if is_group_or_channel(chat_id) and chat_allow_commands_from_users:
            if from_accept_commands and from_accept_this_command:
                return True

        return False

    # Helper function to handle /editMessageText Telegram API commands
    # See main._send_edit_msg()
    def get_update_msg_id(self, id):
        update_msg_id = ""
        if id in self.update_message_id:
            update_msg_id = self.update_message_id[id]
            del self.update_message_id[id]
        return update_msg_id

    def pre_image(self):
        method = self._settings.get(["PreImgMethod"])
        command = self._settings.get(["PreImgCommand"])

        self._logger.debug(f"Starting pre_image. Method: {method}. Command: {command}.")

        if method == "None":
            return
        elif method == "GCODE":
            self._printer.commands(command)
            self._logger.debug("Pre_image gcode command executed")
        elif method == "SYSTEM":
            p = subprocess.Popen(command, shell=True)
            self._logger.debug(f"Pre_image system command executed. PID={p.pid}.")
            while p.poll() is None:
                time.sleep(0.1)
            r = p.returncode
            self._logger.debug(f"Pre_image system command returned: {r}")
        else:
            self._logger.warning(f"Unknown pre_image method: {method}")

    def post_image(self):
        method = self._settings.get(["PostImgMethod"])
        command = self._settings.get(["PostImgCommand"])

        self._logger.debug(f"Starting post_image. Method: {method}. Command: {command}.")

        if method == "None":
            return
        elif method == "GCODE":
            self._printer.commands(command)
            self._logger.debug("Post_image gcode command executed")
        elif method == "SYSTEM":
            p = subprocess.Popen(command, shell=True)
            self._logger.debug(f"Post_image system command executed. PID={p.pid}.")
            while p.poll() is None:
                time.sleep(0.1)
            r = p.returncode
            self._logger.debug(f"Post_image system command returned: {r}")
        else:
            self._logger.warning(f"Unknown post_image method: {method}")

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
            try:
                if self._plugin_manager.get_plugin("multicam", True):
                    self._logger.debug("Getting webcam profiles from multicam")

                    multicam_profiles = self._settings.global_get(["plugins", "multicam", "multicam_profiles"]) or []
                    self._logger.debug(f"Multicam profiles: {multicam_profiles}")

                    for multicam_profile in multicam_profiles:
                        webcam_profile = WebcamProfile(
                            name=multicam_profile.get("name"),
                            snapshot=multicam_profile.get("snapshot"),
                            stream=multicam_profile.get("URL"),
                            flipH=bool(multicam_profile.get("flipH", False)),
                            flipV=bool(multicam_profile.get("flipV", False)),
                            rotate90=bool(multicam_profile.get("rotate90", False)),
                        )
                        webcam_profiles.append(webcam_profile)
            except Exception:
                self._logger.exception("Caught exception getting multicam profiles")

        # Fallback to legacy webcam settings
        if not webcam_profiles:
            try:
                self._logger.debug("Getting webcam profiles from legacy webcam settings")

                webcam_profile = WebcamProfile(
                    name=self._settings.global_get(["webcam", "name"]),
                    snapshot=self._settings.global_get(["webcam", "snapshot"]),
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
                )
                taken_images_contents.append(taken_image_content)
            except Exception:
                self._logger.exception("Caught an exception taking an image")

        return taken_images_contents

    def take_image(self, snapshot_url, flipH=False, flipV=False, rotate=False) -> bytes:
        snapshot_url = urljoin("http://localhost/", snapshot_url)

        self._logger.debug(f"Taking image from url: {snapshot_url}")

        r = requests.get(snapshot_url, timeout=10, verify=False)
        r.raise_for_status()

        image_content = r.content

        if flipH or flipV or rotate:
            self._logger.debug(f"Image transformations [H:{flipH}, V:{flipV}, R:{rotate}]")
            image = Image.open(bytes_reader_class(image_content))
            if flipH:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            if flipV:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            if rotate:
                image = image.transpose(Image.ROTATE_90)
            output = bytes_reader_class()
            image.save(output, format="JPEG")
            image_content = output.getvalue()
            output.close()

        return image_content

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

        self._logger.debug(f"Taking gifs from url: {stream_url}")

        gif_path = os.path.join(self.get_tmpgif_dir(), gif_filename)

        self._logger.debug(f"Removing file {gif_path}")
        try:
            os.remove(gif_path)
        except FileNotFoundError:
            pass

        ffmpeg_path = shutil.which("ffmpeg")
        cpulimiter_path = shutil.which("cpulimit") or shutil.which("limitcpu")

        if not ffmpeg_path:
            self._logger.error("ffmpeg not installed")
            raise RuntimeError("ffmpeg not installed")

        if cpulimiter_path:
            self._logger.debug(f"Using CPU limiter: {cpulimiter_path}")
        else:
            self._logger.error("Neither cpulimit nor limitcpu is installed")
            raise RuntimeError("No CPU limiter (cpulimit or limitcpu) available")

        duration = max(1, min(duration, 60))
        self._logger.debug(f"duration={duration}")

        time_sec = str(datetime.timedelta(seconds=duration))
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

        cmd += [
            cpulimiter_path,
            "-l", str(limit_cpu),
            "-f",
            "-z",
            "--",
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
        subprocess.run(cmd)
        self._logger.debug("Video created")

        return gif_path

    def get_layer_progress_values(self):
        layers = None
        try:
            if self._plugin_manager.get_plugin("DisplayLayerProgress", True):
                headers = {
                    "X-Api-Key": self._settings.global_get(["api", "key"]),
                }
                r = requests.get(
                    f"http://localhost:{self.port}/plugin/DisplayLayerProgress/values",
                    headers=headers,
                    timeout=3,
                )
                r.raise_for_status
                layers = r.json()
            else:
                self._logger.debug("DisplayLayerProgress plugin not installed or disabled")
        except Exception:
            self._logger.exception("Caught an exception in get_layer_progress_values")
        return layers

    def calculate_ETA(self, printTime):
        current_time = datetime.datetime.now()
        finish_time = current_time + datetime.timedelta(seconds=printTime)

        if finish_time.day > current_time.day and finish_time > current_time + datetime.timedelta(days=7):
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

    # Function to be able to do action on gcode
    def hook_gcode_sent(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        if gcode and cmd[:4] == "M600":
            self._logger.info("M600 registered")
            try:
                self.on_event("gCode_M600", {})
            except Exception:
                self._logger.exception("Caught exception on event M600")

    def recv_callback(self, comm_instance, line, *args, **kwargs):
        # Found keyword, fire event and block until other text is received
        if "echo:busy: paused for user" in line or "//action:paused" in line:
            if not self.triggered:
                self.on_event("plugin_pause_for_user_event_notify", {})
                self.triggered = True
        elif "echo:UserNotif" in line:
            self.on_event("UserNotif", {"UserNotif": line[15:]})
        # Other text, we may fire another event if we encounter "paused for user" again
        else:
            self.triggered = False

        return line


# Check that we are running on OctoPrint >= 1.4.0, which introduced the granular permissions system
def get_implementation_class():
    if not is_octoprint_compatible(">=1.4.0"):
        raise Exception("OctoPrint 1.4.0 or greater required.")

    return TelegramPlugin()


__plugin_name__ = "Telegram Notifications"
__plugin_pythoncompat__ = ">=3.6,<4"
__plugin_implementation__ = get_implementation_class()
__plugin_hooks__ = {
    "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    "octoprint.server.http.routes": __plugin_implementation__.route_hook,
    "octoprint.comm.protocol.gcode.received": __plugin_implementation__.recv_callback,
    "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.hook_gcode_sent,
}
