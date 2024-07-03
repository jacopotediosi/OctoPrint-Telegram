import threading, requests, urllib3, re, time, datetime, json, logging, traceback, io, os, pkg_resources, subprocess, zipfile, multiprocessing
import octoprint.plugin, octoprint.util, octoprint.filemanager
from flask_login import current_user
from .telegramCommands import TCMD
from .telegramNotifications import TMSG
from .telegramNotifications import (
    telegramMsgDict,
)  # Dict of known notification messages
from .emojiDict import telegramEmojiDict  # Dict of known emojis
from PIL import Image
from urllib.parse import urljoin


bytes_reader_class = io.BytesIO


####################################################
#        TelegramListener Thread Class
# Connects to Telegram and will listen for messages.
# On incomming message the listener will process it.
####################################################


class TelegramListener(threading.Thread):
    def __init__(self, main):
        threading.Thread.__init__(self)
        self.update_offset = 0
        self.first_contact = True
        self.main = main
        self.do_stop = False
        self.username = "UNKNOWN"
        self._logger = main._logger.getChild("listener")
        self.gEmo = self.main.gEmo

    def run(self):
        self._logger.debug("Try first connect.")
        self.tryFirstContact()
        # Repeat fetching and processing messages until thread stopped
        self._logger.debug("Listener is running.")
        try:
            while not self.do_stop:
                try:
                    self.loop()
                except ExitThisLoopException:
                    pass  # Do nothing, just go to the next loop
        except Exception:
            self._logger.exception("An Exception crashed the Listener.\n")

        self._logger.debug("Listener exits NOW.")

    # Try to get first contact. Repeat every 120sek if no success or stop if task stopped.
    def tryFirstContact(self):
        gotContact = False
        while not self.do_stop and not gotContact:
            try:
                self.username = self.main.test_token()
                gotContact = True
                self.set_status(f"Connected as {self.username}", ok=True)
            except Exception:
                self.set_status(
                    "Got an exception while initially trying to connect to telegram.\n"
                    "Waiting 2 minutes before trying again.\n"
                    f"Traceback: {traceback.format_exc()}"
                )
                time.sleep(120)

    def loop(self):
        json = self.getUpdates()
        try:
            # Seems like we got a message, so lets process it
            for message in json["result"]:
                self.processMessage(message)
        except ExitThisLoopException:
            raise
        # Can't handle the message
        except Exception:
            self._logger.exception("Exception caught!")

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
            self._logger.debug(
                f"Updating update_offset from {self.update_offset} to {1 + new_value}"
            )
            self.update_offset = 1 + new_value
        else:
            self._logger.debug(
                f"Not changing update_offset - otherwise would reduce it from {self.update_offset} to {1 + new_value}"
            )

    def processMessage(self, message):
        self._logger.debug(f"MESSAGE: {message}")
        # Get the update_id to only request newer Messages the next time
        self.set_update_offset(message["update_id"])
        # No message no cookies
        if "message" in message and message["message"].get("chat"):
            chat_id, from_id = self.parseUserData(message)

            # If we come here without a continue (discard message) we have a message from a known and not new user
            # so let's check what he send us.

            # If message is a text message, we probably got a command.
            # When the command is not known, the following handler will discard it.
            if "text" in message["message"]:
                self.handleTextMessage(message, chat_id, from_id)
            # We got no message with text (command) so lets check if we got a file.
            # The following handler will check file and saves it to disk.
            elif "document" in message["message"]:
                self.handleDocumentMessage(message)
            # We got message with notification for a new chat title photo so lets download it
            elif "new_chat_photo" in message["message"]:
                self.handleNewChatPhotoMessage(message)
            # We got message with notification for a deleted chat title photo so we do the same
            elif "delete_chat_photo" in message["message"]:
                self.handleDeleteChatPhotoMessage(message)
            # A member was removed from a group, so lets check if it's our bot and
            # delete the group from our chats if it is
            elif "left_chat_member" in message["message"]:
                self.handleLeftChatMemberMessage(message)
            # At this point we don't know what message type it is, so we do nothing
            else:
                self._logger.warning(
                    f"Got an unknown message. Doing nothing. Data: {message}"
                )
        elif "callback_query" in message:
            self.handleCallbackQuery(message)
        else:
            self._logger.warning(
                "Response is missing .message or .message.chat or callback_query. Skipping it."
            )
            raise ExitThisLoopException()

    def handleCallbackQuery(self, message):
        message["callback_query"]["message"]["text"] = message["callback_query"]["data"]
        chat_id, from_id = self.parseUserData(message["callback_query"])
        self.handleTextMessage(message["callback_query"], chat_id, from_id)

    def handleLeftChatMemberMessage(self, message):
        self._logger.debug("Message Del_Chat")
        if (
            message["message"]["left_chat_member"]["username"] == self.username[1:]
            and str(message["message"]["chat"]["id"]) in self.main.chats
        ):
            del self.main.chats[str(message["message"]["chat"]["id"])]
            # Do a self._settings.save() ???
            self._logger.debug("Chat deleted")

    def handleDeleteChatPhotoMessage(self, message):
        self._logger.debug("Message Del_Chat_Photo")
        path_to_remove = os.path.join(
            self.main.get_plugin_data_folder(),
            "img",
            "user",
            os.path.basename(f"pic{message['message']['chat']['id']}.jpg"),
        )
        self._logger.info(f"Removing file {path_to_remove}")
        try:
            os.remove(path_to_remove)
        except OSError:
            self._logger.exception(f"Failed to remove file {path_to_remove}")

    def handleNewChatPhotoMessage(self, message):
        self._logger.debug("Message New_Chat_Photo")
        chat_id = message["message"]["chat"]["id"]
        # Only if we know the chat
        if str(chat_id) in self.main.chats:
            self._logger.debug(f"New_Chat_Photo Found User. Chat id: {chat_id}")
            kwargs = {
                "chat_id": int(message["message"]["chat"]["id"]),
                "file_id": message["message"]["new_chat_photo"][0]["file_id"],
            }
            t = threading.Thread(target=self.main.get_usrPic, kwargs=kwargs)
            t.daemon = True
            t.run()

    def handleDocumentMessage(self, message):
        try:
            self._logger.debug("Handling document message")

            chat_id = str(message["message"]["chat"]["id"])
            from_id = str(message["message"]["from"]["id"])

            uploaded_file_filename = os.path.basename(
                message["message"]["document"]["file_name"]
            )

            # Check if upload command is allowed
            if not self.main.isCommandAllowed(chat_id, from_id, "/upload"):
                self._logger.warning(
                    f"Received file {uploaded_file_filename} from an unauthorized user"
                )
                self.main.send_msg(
                    f"{self.gEmo('warning')} You are not authorized to upload files",
                    chatID=chat_id,
                )
                return

            # Check the file extension
            is_zip_file = False
            if not octoprint.filemanager.valid_file_type(
                uploaded_file_filename, "machinecode"
            ):
                if uploaded_file_filename.lower().endswith(".zip"):
                    is_zip_file = True
                else:
                    self._logger.warning(
                        f"Received file {uploaded_file_filename} with invalid extension"
                    )
                    self.main.send_msg(
                        f"{self.gEmo('warning')} Sorry, I only accept files with .gcode, .gco or .g or .zip extension",
                        chatID=chat_id,
                    )
                    return

            # Download the uploaded file
            self.main.send_msg(
                f"{self.gEmo('save')} Saving file {uploaded_file_filename}...",
                chatID=chat_id,
            )
            uploaded_file_content = self.main.get_file(
                message["message"]["document"]["file_id"]
            )

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
                            if not octoprint.filemanager.valid_file_type(
                                member_filename, "machinecode"
                            ):
                                self._logger.debug(
                                    f"Ignoring file {member_filename} while extracting a zip because it has an invalid extension"
                                )
                                continue

                            member_content = zf.read(member)
                            destination_file_relative_path = os.path.join(
                                destination_folder, member_filename
                            )
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
                            self._logger.info(
                                f"Added file to {added_file_relative_path}"
                            )

                            added_files_relative_paths.append(
                                destination_file_relative_path
                            )
                        except Exception:
                            self._logger.exception(
                                f"Exception while extracting file {member_filename} contained in the zip"
                            )
            else:
                destination_file_relative_path = os.path.join(
                    destination_folder, uploaded_file_filename
                )
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
                response_message = f"{self.gEmo('upload')} I've successfully saved the file(s) you sent me as {', '.join(added_files_relative_paths)}"
            else:
                response_message = f"{self.gEmo('warning')} No files were added. Did you upload an empty zip?"

            # If there are multiple files or the "select file after upload" settings is off
            if len(added_files_relative_paths) != 1 or not self.main._settings.get(
                ["selectFileUpload"]
            ):
                # Just send the message
                self.main.send_msg(
                    response_message,
                    chatID=chat_id,
                    msg_id=self.main.getUpdateMsgId(chat_id),
                )

            # If instead only one file has been added and the "select file after upload" settings is off
            else:
                # Check if printer is ready
                if not self.main._printer.is_ready():
                    response_message += (
                        " but I can't load it because the printer is not ready"
                    )
                    self.main.send_msg(
                        response_message,
                        chatID=chat_id,
                        msg_id=self.main.getUpdateMsgId(chat_id),
                    )
                    return

                # Load the uploaded file
                try:
                    file_to_select_abs_path = self.main._file_manager.path_on_disk(
                        octoprint.filemanager.FileDestinations.LOCAL,
                        added_files_relative_paths[0],
                    )
                    self._logger.debug(f"Selecting file: {file_to_select_abs_path}")
                    self.main._printer.select_file(
                        file_to_select_abs_path, sd=False, printAfterSelect=False
                    )
                except Exception:
                    response_message += " but I wasn't able to load the file"
                    self.main.send_msg(
                        response_message,
                        chatID=chat_id,
                        msg_id=self.main.getUpdateMsgId(chat_id),
                    )
                    return

                # Ask the user whether to print the loaded file
                response_message += (
                    " and it is loaded.\n\n"
                    f"{self.gEmo('question')} Do you want me to start printing it now?"
                )
                self.main.send_msg(
                    response_message,
                    noMarkup=True,
                    msg_id=self.main.getUpdateMsgId(chat_id),
                    responses=[
                        [
                            [
                                f"{self.main.emojis['check']} Print",
                                "/print_s",
                            ],
                            [
                                f"{self.main.emojis['cross mark']} Cancel",
                                "/print_x",
                            ],
                        ]
                    ],
                    chatID=chat_id,
                )
        except Exception:
            self._logger.exception("Exception occured while processing a file")
            self.main.send_msg(
                (
                    f"{self.gEmo('warning')} Something went wrong during processing of your file.\n"
                    f"{self.gEmo('mistake')} Sorry. More details are in octoprint.log."
                ),
                chatID=chat_id,
            )

    def handleTextMessage(self, message, chat_id, from_id):
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
        if any(
            (f"{k}_") in command
            for k, v in self.main.tcmd.commandDict.items()
            if "param" in v
        ):
            parameter = "_".join(command.split("_")[1:])
            command = command.split("_")[0]
        self._logger.info(
            f"Got a command: '{command}' with parameter: '{parameter}' in chat id  {message['message']['chat']['id']}"
        )
        # Is command  known?
        if command not in self.main.tcmd.commandDict:
            # we dont know the command so skip the message
            self._logger.warning("Previous command was an unknown command.")
            if not self.main._settings.get(["no_mistake"]):
                self.main.send_msg(
                    f"I do not understand you! {self.gEmo('mistake')}", chatID=chat_id
                )
            raise ExitThisLoopException()
        # Check if user is allowed to execute the command
        if self.main.isCommandAllowed(chat_id, from_id, command):
            # Identify user
            try:
                user = f"{message['message']['chat']['first_name']} {message['message']['chat']['last_name']}"
            except:
                user = ""
            # Execute command
            self.main.tcmd.commandDict[command]["cmd"](
                chat_id, from_id, command, parameter, user
            )
        else:
            # User was not alloed to execute this command
            self._logger.warning("Previous command was from an unauthorized user.")
            self.main.send_msg(
                f"You are not allowed to do this! {self.gEmo('notallowed')}",
                chatID=chat_id,
            )

    def parseUserData(self, message):
        self.main.chats = self.main._settings.get(["chats"])
        chat = message["message"]["chat"]
        chat_id = str(chat["id"])
        data = self.main.newChat  # Data for new user
        # If we know the user or chat, overwrite data with user data
        if chat_id in self.main.chats:
            data = self.main.chats[chat_id]
        # Update data or get data for new user
        data["type"] = chat["type"].upper()
        if chat["type"] == "group" or chat["type"] == "supergroup":
            data["private"] = False
            data["title"] = chat["title"]
        elif chat["type"] == "private":
            data["private"] = True
            data["title"] = ""
            if "first_name" in chat:
                data["title"] += f"{chat['first_name']} - "
            if "last_name" in chat:
                data["title"] += f"{chat['last_name']} - "
            if "username" in chat:
                data["title"] += f"@{chat['username']}"
        from_id = chat_id
        # If message is from a group, chat_id will be left as id of group
        # and from_id is set to id of user who send the message
        if not data["private"]:
            if "from" in message:
                from_id = str(message["from"]["id"])
            else:
                from_id = str(message["message"]["from"]["id"])
            # If group accepts only commands from known users (allow_users = true, accept_commands=false)
            # and user is not in known chats, then they are unknown and we dont want to listen to them
            if chat_id in self.main.chats:
                if (
                    self.main.chats[chat_id]["allow_users"]
                    and from_id not in self.main.chats
                    and not self.main.chats[chat_id]["accept_commands"]
                ):
                    self._logger.warning("Previous command was from an unknown user.")
                    self.main.send_msg(
                        f"I don't know you! Certainly you are a nice Person {self.gEmo('heart')}",
                        chatID=chat_id,
                    )
                    raise ExitThisLoopException()
        # If we dont know the user or group, create new user.
        # Send welcome message and skip message.
        if chat_id not in self.main.chats:
            self.main.chats[chat_id] = data
            self.main.send_msg(
                f"{self.gEmo('info')} Now I know you. Before you can do anything, go to OctoPrint Settings and edit some rights.",
                chatID=chat_id,
            )
            kwargs = {"chat_id": int(chat_id)}
            t = threading.Thread(target=self.main.get_usrPic, kwargs=kwargs)
            t.daemon = True
            t.run()
            self._logger.debug("Got new User")
            raise ExitThisLoopException()
        return (chat_id, from_id)

    def getUpdates(self):
        self._logger.debug(
            f"listener: sending request with offset {self.update_offset}..."
        )
        req = None

        # Try to check for incoming messages. Wait 120sek and repeat on failure.
        try:
            if self.update_offset == 0 and self.first_contact:
                res = ["0", "0"]
                while len(res) > 0:
                    req = requests.get(
                        f"{self.main.bot_url}/getUpdates",
                        params={"offset": self.update_offset, "timeout": 0},
                        allow_redirects=False,
                        timeout=10,
                        proxies=self.getProxies(),
                    )
                    json = req.json()
                    if not json["ok"]:
                        self.set_status(
                            f"Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: {json}"
                        )
                        time.sleep(120)
                        raise ExitThisLoopException()
                    if len(json["result"]) > 0 and "update_id" in json["result"][0]:
                        self.set_update_offset(json["result"][0]["update_id"])
                    res = json["result"]
                    if len(res) < 1:
                        self._logger.debug(
                            "Ignoring message because first_contact is True."
                        )
                if self.update_offset == 0:
                    self.set_update_offset(0)
            else:
                req = requests.get(
                    f"{self.main.bot_url}/getUpdates",
                    params={"offset": self.update_offset, "timeout": 30},
                    allow_redirects=False,
                    timeout=40,
                    proxies=self.getProxies(),
                )
        except requests.exceptions.Timeout:
            # Just start the next loop
            raise ExitThisLoopException()
        except Exception:
            self.set_status(
                "Got an exception while trying to connect to telegram API.\n"
                "Waiting 2 minutes before trying again.\n"
                f"Stacktrace: {traceback.format_exc()}"
            )
            time.sleep(120)
            raise ExitThisLoopException()
        if req.status_code != 200:
            self.set_status(
                f"Telegram API responded with code {req.status_code}. Waiting 2 minutes before trying again."
            )
            time.sleep(120)
            raise ExitThisLoopException()
        if req.headers["content-type"] != "application/json":
            self.set_status(
                f"Unexpected Content-Type. Expected: application/json. Was: {req.headers['content-type']}. Waiting 2 minutes before trying again."
            )
            time.sleep(120)
            raise ExitThisLoopException()
        json = req.json()
        if not json["ok"]:
            self.set_status(
                f"Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: {json}"
            )
            time.sleep(120)
            raise ExitThisLoopException()
        if "result" in json and len(json["result"]) > 0:
            for entry in json["result"]:
                self.set_update_offset(entry["update_id"])
        return json

    # Stop the listener
    def stop(self):
        self.do_stop = True

    def set_status(self, status, ok=False):
        if status != self.main.connection_state_str:
            if self.do_stop:
                self._logger.debug(f"Would set status but do_stop is True: {status}")
                return
            if ok:
                self._logger.debug(f"Setting status: {status}")
            else:
                self._logger.error(f"Setting status: {status}")
        self.connection_ok = ok
        self.main.connection_state_str = status

    def getProxies(self):
        http_proxy = self.main._settings.get(["http_proxy"])
        https_proxy = self.main._settings.get(["https_proxy"])
        return {"http": http_proxy, "https": https_proxy}


class TelegramPluginLoggingFilter(logging.Filter):
    def filter(self, record):
        for match in re.findall("[0-9]+:[a-zA-Z0-9_\-]+", record.msg):
            new = re.sub(
                "[0-9]", "1", re.sub("[a-z]", "a", re.sub("[A-Z]", "A", match))
            )
            record.msg = record.msg.replace(match, new)
        return True


class ExitThisLoopException(Exception):
    pass


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
):
    def __init__(self, version):
        self.version = float(version)
        # For more init stuff see on_after_startup()
        self.thread = None
        self.bot_url = None
        self.chats = {}
        self.connection_state_str = "Disconnected."
        self.connection_ok = False
        urllib3.disable_warnings()
        self.updateMessageID = {}
        self.shut_up = {}
        self.send_messages = True
        self.tcmd = None
        self.tmsg = None
        self.sending_okay_minute = None
        self.sending_okay_count = 0
        # Initial settings for new chat. See on_after_startup()
        # !!! sync with newUsrDict in on_settings_migrate() !!!
        self.newChat = {}
        # Use of emojis see below at method gEmo()
        self.emojis = {
            "octo": "\U0001F419",  # Octopus
            "mistake": "\U0001F616",
            "notify": "\U0001F514",
            "shutdown": "\U0001F4A4",
            "shutup": "\U0001F64A",
            "noNotify": "\U0001F515",
            "notallowed": "\U0001F62C",
            "rocket": "\U0001F680",
            "save": "\U0001F4BE",
            "heart": "\U00002764",
            "info": "\U00002139",
            "settings": "\U0001F4DD",
            "clock": "\U000023F0",
            "height": "\U00002B06",
            "question": "\U00002753",
            "warning": "\U000026A0",
            "enter": "\U0000270F",
            "upload": "\U0001F4E5",
            "check": "\U00002705",
            "lamp": "\U0001F4A1",
            "movie": "\U0001F3AC",
            "finish": "\U0001F3C1",
            "cam": "\U0001F3A6",
            "hooray": "\U0001F389",
            "error": "\U000026D4",
            "play": "\U000025B6",
            "stop": "\U000025FC",
        }
        self.emojis.update(telegramEmojiDict)

    # All emojis will be get via this method to disable them globaly by the corrosponding setting.
    # So if you want to use emojis anywhere use gEmo("...") instead of emojis["..."].
    def gEmo(self, key):
        if self._settings.get(["send_icon"]) and key in self.emojis:
            return self.emojis[key]
        return ""

    # Starts the telegram listener thread
    def start_listening(self):
        if self._settings.get(["token"]) != "" and self.thread is None:
            self._logger.debug("Starting listener.")
            self.bot_url = (
                f"https://api.telegram.org/bot{self._settings.get(['token'])}"
            )
            self.bot_file_url = (
                f"https://api.telegram.org/file/bot{self._settings.get(['token'])}"
            )
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
            self._logger.warning(
                "Sent more than 10 messages in the last minute. Shutting down..."
            )
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
        return dict(js=["js/telegram.js"])

    ##########
    ### Template API
    ##########

    def get_template_configs(self):
        return [dict(type="settings", name="Telegram", custom_bindings=True)]

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

    def on_after_startup(self):
        self._logger.addFilter(TelegramPluginLoggingFilter())

        self.tcmd = TCMD(self)
        self.triggered = False

        # Notification Message Handler class. called only by on_event()
        self.tmsg = TMSG(self)

        # Initial settings for new chat.
        # !!! sync this dict with newUsrDict in on_settings_migrate() !!!
        self.newChat = {
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
                        self._logger.exception(
                            f"Exception caught removing file {file_path}"
                        )

        # Update user profile photos
        for key in self.chats:
            try:
                if key != "zBOTTOMOFCHATS":
                    kwargs = {}
                    kwargs["chat_id"] = int(key)
                    t = threading.Thread(target=self.get_usrPic, kwargs=kwargs)
                    t.daemon = True
                    t.run()
            except Exception:
                pass

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
            tracking_token=None,
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
            multicam=False,
            no_mistake=False,
            scale_gif=0,
            delay_img_gif=0.5,
            number_img_gif=20,
            frame_img_gif=15,
            fileOrder=False,
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
        # !!! sync this dict with newChat in on_after_startup() !!!
        newUsrDict = {
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
        chats = {
            k: v
            for k, v in self._settings.get(["chats"]).items()
            if k != "zBOTTOMOFCHATS"
        }
        self._logger.debug(f"LOADED CHATS: {chats}")
        self._settings.set(["chats"], {})
        if current is None or current < 1:
            ########## Update Chats
            # There shouldn't be any chats, but maybe somone had installed any test branch.
            # Then we have to check if all needed settings are populated.
            for chat in chats:
                for setting in newUsrDict:
                    if setting not in chats[chat]:
                        if setting == "commands":
                            chats[chat]["commands"] = {
                                k: False
                                for k, v in tcmd.commandDict.items()
                                if "bind_none" not in v
                            }
                        elif setting == "notifications":
                            chats[chat]["notifications"] = {
                                k: False for k, v in telegramMsgDict.items()
                            }
                        else:
                            chats[chat][setting] = False
            ########## Is there a chat from old single user plugin version?
            # Then migrate it into chats.
            chat = self._settings.get(["chat"])
            if chat is not None:
                self._settings.set(["chat"], None)
                data = {}
                data.update(newUsrDict)
                data["private"] = True
                data["title"] = "[UNKNOWN]"
                # Try to get infos from telegram by sending a "you are migrated" message
                try:
                    message = {}
                    message["text"] = (
                        f"The OctoPrint Plugin {self._plugin_name} has been updated to new Version {self._plugin_version}.\n\n"
                        f"Please open your {self._plugin_name} settings in OctoPrint and set configurations for this chat.\n\n"
                        "Until then you are not able to send or receive anything useful with this Bot.\n\n"
                        "More informations on: https://github.com/jacopotediosi/OctoPrint-Telegram"
                    )
                    message["chat_id"] = chat
                    message["disable_web_page_preview"] = True
                    r = requests.post(
                        f"{self.bot_url}/sendMessage",
                        data=message,
                        proxies=self.getProxies(),
                    )
                    r.raise_for_status()
                    if r.headers["content-type"] != "application/json":
                        raise Exception("invalid content-type")
                    json = r.json()
                    if not json["ok"]:
                        raise Exception("invalid request")
                    chat = json["result"]["chat"]
                    if chat["type"] == "group":
                        data["private"] = False
                        data["title"] = chat["title"]
                    elif chat["type"] == "private":
                        data["private"] = True
                        data["title"] = ""
                        if "first_name" in chat:
                            data["title"] += f"{chat['first_name']} - "
                        if "last_name" in chat:
                            data["title"] += f"{chat['last_name']} - "
                        if "username" in chat:
                            data["title"] += f"@{chat['username']}"
                except Exception:
                    self._logger.exception(
                        "ERROR migrating chat. Done with defaults private=true,title=[UNKNOWN]"
                    )
                # Place the migrated chat in chats
                chats.update({str(chat["id"]): data})
            self._logger.debug(f"MIGRATED Chats: {chats}")
            ########## Update messages. Old text will be taken to new structure.
            messages = self._settings.get(["messages"])
            msgOut = {}
            for msg in messages:
                if msg == "TelegramSendNotPrintingStatus":
                    msg2 = "StatusNotPrinting"
                elif msg == "TelegramSendPrintingStatus":
                    msg2 = "StatusPrinting"
                else:
                    msg2 = msg
                if type(messages[msg]) is not type({}):
                    newMsg = telegramMsgDict[msg2].copy()
                    newMsg["text"] = str(messages[msg])
                    msgOut.update({msg2: newMsg})
                else:
                    msgOut.update({msg2: messages[msg]})
            self._settings.set(["messages"], msgOut)
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
                    chats[chat]["commands"].update(
                        {"/files": chats[chat]["commands"]["/list"]}
                    )
                if "/imsorrydontshutup" in chats[chat]["commands"]:
                    chats[chat]["commands"].update(
                        {"/dontshutup": chats[chat]["commands"]["/imsorrydontshutup"]}
                    )
                if "type" not in chats[chat]:
                    chats[chat].update(
                        {"type": "PRIVATE" if chats[chat]["private"] else "GROUP"}
                    )
                delCmd = []
                # Collect remove 'bind_none' commands
                for cmd in tcmd.commandDict:
                    if (
                        cmd in chats[chat]["commands"]
                        and "bind_none" in tcmd.commandDict[cmd]
                    ):
                        delCmd.append(cmd)
                # Collect Delete commands from settings if they don't belong to commandDict anymore
                for cmd in chats[chat]["commands"]:
                    if cmd not in tcmd.commandDict:
                        delCmd.append(cmd)
                # Finally delete commands
                for cmd in delCmd:
                    del chats[chat]["commands"][cmd]
                # If there are new commands in comamndDict, add them to settings
                for cmd in tcmd.commandDict:
                    if cmd not in chats[chat]["commands"]:
                        if "bind_none" not in tcmd.commandDict[cmd]:
                            chats[chat]["commands"].update({cmd: False})
                # Delete notifications from settings if they don't belong to msgDict anymore
                delMsg = []
                for msg in chats[chat]["notifications"]:
                    if msg not in telegramMsgDict:
                        delMsg.append(msg)
                for msg in delMsg:
                    del chats[chat]["notifications"][msg]
                # If there are new notifications in msgDict, add them to settings
                for msg in telegramMsgDict:
                    if msg not in chats[chat]["notifications"]:
                        chats[chat]["notifications"].update({msg: False})
            self._settings.set(["chats"], chats)

            ########## If anything changed in telegramMsgDict, we also have to update settings for messages
            messages = self._settings.get(["messages"])
            # This for loop deletes items from messages settings
            # if they dont't belong to telegramMsgDict anymore
            delMsg = []
            for msg in messages:
                if msg not in telegramMsgDict:
                    delMsg.append(msg)
            for msg in delMsg:
                del messages[msg]
            # This for loop adds new message settings from telegramMsgDict to settings
            for msg in telegramMsgDict:
                if msg not in messages:
                    messages.update({msg: telegramMsgDict[msg]})
                elif "combined" not in messages[msg]:
                    messages[msg].update({"combined": True})

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
        if "chats" in data and data["chats"]:
            delList = []
            for key in data["chats"]:
                if "new" in data["chats"][key]:
                    data["chats"][key]["new"] = False
                # Look for deleted chats
                if not key in self.chats and not key == "zBOTTOMOFCHATS":
                    delList.append(key)
            # Delete chats finally
            for key in delList:
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
            if not re.match("^[0-9]+:[a-zA-Z0-9_\-]+$", data["token"]):
                self._logger.error(
                    "Not saving token because it doesn't seem to have the right format."
                )
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
        restricted = (("token", None), ("tracking_token", None), ("chats", dict()))
        for r, v in restricted:
            if r in data and (
                current_user is None
                or current_user.is_anonymous()
                or not current_user.is_admin()
            ):
                data[r] = v

        return data

    def get_settings_restricted_paths(self):
        # Only used in OctoPrint versions > 1.2.16
        return dict(admin=[["token"], ["tracking_token"], ["chats"]])

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
                self._logger.debug(
                    f"Received a known event: {event} - Payload: {payload}"
                )
                self.tmsg.startEvent(event, payload, **kwargs)
        except Exception:
            self._logger.exception("Caught exception while handling an event")

    ##########
    ### SimpleApi API
    ##########

    def get_api_commands(self):
        return dict(
            testToken=["token"],
            testEvent=["event"],
            delChat=["ID"],
            setCommandList=["force"],
        )

    def on_api_get(self, request):
        # Got an user-update with this command, so lets do that
        if (
            "id" in request.args
            and "cmd" in request.args
            and "note" in request.args
            and "allow" in request.args
        ):
            self.chats[request.args["id"]]["accept_commands"] = self.str2bool(
                str(request.args["cmd"])
            )
            self.chats[request.args["id"]]["send_notifications"] = self.str2bool(
                str(request.args["note"])
            )
            self.chats[request.args["id"]]["allow_users"] = self.str2bool(
                str(request.args["allow"])
            )
            self._logger.debug(f"Updated chat - {request.args['id']}")
        elif "bindings" in request.args:
            bind_text = {}
            for key in {k: v for k, v in telegramMsgDict.items() if "bind_msg" in v}:
                if telegramMsgDict[key]["bind_msg"] in bind_text:
                    bind_text[telegramMsgDict[key]["bind_msg"]].append(key)
                else:
                    bind_text[telegramMsgDict[key]["bind_msg"]] = [key]
            return json.dumps(
                {
                    "bind_cmd": [
                        k
                        for k, v in self.tcmd.commandDict.items()
                        if "bind_none" not in v
                    ],
                    "bind_msg": [
                        k for k, v in telegramMsgDict.items() if "bind_msg" not in v
                    ],
                    "bind_text": bind_text,
                    "no_setting": [
                        k for k, v in telegramMsgDict.items() if "no_setting" in v
                    ],
                }
            )

        retChats = {
            k: v
            for k, v in self.chats.items()
            if "delMe" not in v and k != "zBOTTOMOFCHATS"
        }
        for chat in retChats:
            if os.path.isfile(
                os.path.join(
                    self.get_plugin_data_folder(),
                    "img",
                    "user",
                    os.path.basename(f"pic{chat}.jpg"),
                )
            ):
                retChats[chat]["image"] = f"/plugin/telegram/img/user/pic{chat}.jpg"
            elif int(chat) < 0:
                retChats[chat]["image"] = "/plugin/telegram/static/img/group.jpg"
            else:
                retChats[chat]["image"] = "/plugin/telegram/static/img/default.jpg"

        return json.dumps(
            {
                "chats": retChats,
                "connection_state_str": self.connection_state_str,
                "connection_ok": self.connection_ok,
            }
        )

    def on_api_command(self, command, data):
        if command == "testToken":
            self._logger.debug(f"Testing token {data['token']}")
            try:
                if self._settings.get(["token"]) != data["token"]:
                    username = self.test_token(data["token"])
                    self._settings.set(["token"], data["token"])
                    self.stop_listening()  # To start with new token if already running
                    self.start_listening()
                    return json.dumps(
                        {
                            "ok": True,
                            "connection_state_str": f"Token valid for {username}.",
                            "error_msg": None,
                            "username": username,
                        }
                    )
                return json.dumps(
                    {
                        "ok": True,
                        "connection_state_str": f"Token valid for {self.thread.username}.",
                        "error_msg": None,
                        "username": self.thread.username,
                    }
                )
            except Exception as e:
                return json.dumps(
                    {
                        "ok": False,
                        "connection_state_str": f"Error:{e}",
                        "username": None,
                        "error_msg": str(e),
                    }
                )
        # Delete a chat (will not be removed and show up again on octorint restart
        # if save button is not pressed on settings dialog)
        elif command == "delChat":
            strId = str(data["ID"])
            if strId in self.chats:
                del self.chats[strId]
                # Do self._settings.save() here???????
            return json.dumps(
                {
                    "chats": {
                        k: v
                        for k, v in self.chats.items()
                        if "delMe" not in v and k != "zBOTTOMOFCHATS"
                    },
                    "connection_state_str": self.connection_state_str,
                    "connection_ok": self.connection_ok,
                }
            )
        elif command == "testEvent":
            self._logger.debug(f"Testing event {data['event']}")
            try:
                self.on_event(data["event"], {})
                return json.dumps({"ok": True, "error_msg": None})
            except Exception as e:
                return json.dumps({"ok": False, "username": None, "error_msg": str(e)})
        elif command == "setCommandList":
            self._logger.debug("Set default command for bot")
            try:
                self.setMyCommands(True)
                self._logger.debug("Set default command for bot done will return ok")
                return json.dumps(
                    {
                        "ok": True,
                        "setMyCommands_state_str": "SetMyCommands done",
                        "error_msg": None,
                    }
                )
            except Exception as e:
                return json.dumps(
                    {
                        "ok": False,
                        "setMyCommands_state_str": f"Error: {e}",
                        "error_msg": str(e),
                    }
                )

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
                self._logger.debug(
                    f"Send_msg() found event: {kwargs['event']} | chats list={self.chats}"
                )
                for key in self.chats:
                    self._logger.debug(f"send_msg loop key = {key}")
                    if key != "zBOTTOMOFCHATS":
                        try:
                            self._logger.debug(
                                f"self.chats[key]['notifications'] = {self.chats[key]['notifications']}"
                            )
                            if (
                                self.chats[key]["notifications"][kwargs["event"]]
                                and (key not in self.shut_up or self.shut_up[key] == 0)
                                and self.chats[key]["send_notifications"]
                            ):
                                kwargs["chatID"] = key
                                threading.Thread(
                                    target=self._send_msg, kwargs=kwargs
                                ).run()
                        except Exception:
                            self._logger.exception(
                                f"Caught an exception in loop chatId for key: {key}"
                            )
            # Seems to be a broadcast
            elif "chatID" not in kwargs:
                for key in self.chats:
                    kwargs["chatID"] = key
                    threading.Thread(target=self._send_msg, kwargs=kwargs).run()
            # This is a 'editMessageText' message
            elif (
                "msg_id" in kwargs
                and kwargs["msg_id"] != ""
                and kwargs["msg_id"] is not None
            ):
                threading.Thread(target=self._send_edit_msg, kwargs=kwargs).run()
            # Direct message or event notification to a chat_id
            else:
                threading.Thread(target=self._send_msg, kwargs=kwargs).run()
        except Exception:
            self._logger.exception("Caught an exception in send_msg()")

    # This method is used to update a message text of a sent message.
    # The sent message had to have no_markup = true when calling send_msg() (otherwise it would not work)
    # by setting no_markup = true we got a messageg_id on sending the message which is saved in selfupdateMessageID.
    # If this message_id is passed in msg_id to send_msg() then this method will be called.
    def _send_edit_msg(
        self,
        message="",
        msg_id="",
        chatID="",
        responses=None,
        inline=True,
        markup=None,
        delay=0,
        **kwargs,
    ):
        if not self.send_messages:
            return

        if delay > 0:
            time.sleep(delay)
        try:
            self._logger.debug(
                "Sending a message UPDATE in chat {chatID}: {message}".format(
                    message=message.replace("\n", "\\n"), chatID=chatID
                )
            )
            data = {}
            data["text"] = message
            data["message_id"] = msg_id
            data["chat_id"] = int(chatID)
            if markup:
                if markup == "HTML" or markup == "Markdown" or markup == "MarkdownV2":
                    data["parse_mode"] = markup
                else:
                    self._logger.warning(f"Invalid markup: {markup}")
            if responses and inline:
                myArr = []
                for k in responses:
                    myArr.append([{"text": x[0], "callback_data": x[1]} for x in k])
                keyboard = {"inline_keyboard": myArr}
                data["reply_markup"] = json.dumps(keyboard)
            self._logger.debug(f"SENDING UPDATE: {data}")
            req = requests.post(
                f"{self.bot_url}/editMessageText", data=data, proxies=self.getProxies()
            )
            if req.headers["content-type"] != "application/json":
                self._logger.warning(
                    f"Unexpected Content-Type. Expected: application/json. Was: {req.headers['content-type']}. Waiting 2 minutes before trying again."
                )
                return
            myJson = req.json()
            self._logger.debug(f"REQUEST RES: {myJson}")
            if inline:
                self.updateMessageID[chatID] = msg_id
        except Exception:
            self._logger.exception("Caught an exception in _send_edit_msg()")

    def _send_msg(
        self,
        message="",
        with_image=False,
        with_gif=False,
        responses=None,
        delay=0,
        inline=True,
        chatID="",
        markup=None,
        showWeb=False,
        silent=False,
        **kwargs,
    ):
        if not self.send_messages:
            return

        self._logger.debug("start _send_msg")

        # PreImgMethod
        try:
            if with_image or with_gif:
                premethod = self._settings.get(["PreImgMethod"])
                self._logger.debug(f"PreImgMethod {premethod}")
                precommand = self._settings.get(["PreImgCommand"])
                if premethod == "GCODE":
                    self._logger.debug(f"PreImgCommand {precommand}")
                    self._printer.commands(precommand)
                    self._logger.debug("PreImg gcode command executed")
                elif premethod == "SYSTEM":
                    self._logger.debug(f"PreImgCommand {precommand}")
                    p = subprocess.Popen(precommand, shell=True)
                    self._logger.debug(
                        f"PreImg system command executed. PID={p.pid}, Command={precommand}"
                    )
                    while p.poll() is None:
                        time.sleep(0.1)
                        r = p.returncode
                        self._logger.debug(f"PreImg system command returned: {r}")
        except Exception:
            self._logger.exception("Exception PreImgMethod")

        if delay > 0:
            time.sleep(delay)

        try:
            if with_image:
                if "event" in kwargs and not self._settings.get(
                    ["messages", kwargs["event"], "combined"]
                ):
                    args = locals()
                    del args["kwargs"]["event"]
                    del args["self"]
                    args["message"] = ""
                    self._logger.debug("Sending image...")
                    threading.Thread(target=self._send_msg, kwargs=args).run()
                    args["message"] = message
                    args["with_image"] = False
                    self._logger.debug("Sending text...")
                    threading.Thread(target=self._send_msg, kwargs=args).run()
                    return

            self._logger.debug("log instead log sending message ")
            # self._logger.info(f"Sending a message: {message.replace('\n', '\\n')} with_image={with_image} with_gif={with_gif} chatID={chatID}")

            data = {}

            data["disable_web_page_preview"] = not showWeb
            data["chat_id"] = chatID
            data["disable_notification"] = silent

            if markup:
                if markup == "HTML" or markup == "Markdown" or markup == "MarkdownV2":
                    message_data["parse_mode"] = markup
                else:
                    self._logger.warning(f"Invalid markup: {markup}")

            if responses:
                myArr = []
                for k in responses:
                    myArr.append([{"text": x[0], "callback_data": x[1]} for x in k])
                keyboard = {"inline_keyboard": myArr}
                data["reply_markup"] = json.dumps(keyboard)

            if with_gif:
                try:
                    sendOneInLoop = False
                    if kwargs["event"] == "plugin_octolapse_movie_done":
                        kwargs["event"] = "MovieDone"
                    if kwargs["event"] == "MovieDone":
                        ret = kwargs["movie"]
                        # file = self._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, ret)
                        file = ret
                        file_size = os.path.getsize(file)
                        humanFileSize = self.humanbytes(file_size)
                        self._logger.info(f"File Size is : {humanFileSize}")
                        if file_size > 50000000:  # 50MB
                            ret = ""
                            self._logger.debug(
                                f"Sending without image... ChatID: {chatID}"
                            )
                            data["text"] = (
                                f"{message} but file size is {humanFileSize} so we cannot send it with the message"
                            )
                            r = requests.post(
                                f"{self.bot_url}/sendMessage",
                                data=data,
                                proxies=self.getProxies(),
                            )
                            self._logger.debug(f"Sending finished. {r.status_code}")
                    else:
                        self._logger.info("Will try to create a gif ")

                        # requests.get(f"{self.main.bot_url}/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'}, proxies=self.getProxies())
                        if self._plugin_manager.get_plugin(
                            "multicam", True
                        ) and self._settings.get(["multicam"]):
                            try:
                                curr = self._settings.global_get(
                                    ["plugins", "multicam", "multicam_profiles"]
                                )
                                self._logger.debug(f"multicam_profiles : {curr}")
                                ListGif = []
                                for li in curr:
                                    try:
                                        self._logger.debug(f"multicam profile : {li}")
                                        url = li.get("URL")
                                        self._logger.debug(f"multicam URL : {url}")
                                        ret = self.create_gif_new(chatID, 0, li)
                                        if ret != "":
                                            ListGif.append(ret)
                                            # if not sendOneInLoop:
                                            # 	self.send_file(chatID, ret,message)
                                            # else:
                                            # 	self.send_file(chatID, ret,"")
                                            # sendOneInLoop = True
                                    except Exception:
                                        self._logger.exception(
                                            "Exception loop multicam URL to create gif"
                                        )
                                ret = ListGif[-1]
                                self._logger.debug(f"ListGif: {ListGif}")
                                for x in ListGif:
                                    try:
                                        if x != ret:
                                            self._logger.debug(
                                                f"send_file whithout message: {x}"
                                            )
                                            self.send_file(chatID, x, "")
                                    except Exception:
                                        self._logger.exception(
                                            "Exception loop multicam URL to send gif"
                                        )

                            except Exception:
                                self._logger.exception(
                                    "Exception occured on getting multicam options"
                                )
                        else:
                            ret = self.create_gif_new(chatID, 0, 0)

                        if ret == "":
                            ret = self.create_gif_new(chatID, 0, 0)

                    if ret != "" and not sendOneInLoop:
                        self._logger.debug(f"send_video with message: {ret}")
                        self.send_video(chatID, ret, message)
                        # ret = self.create_gif_new(chatID,0,0)
                        # if ret != "":
                        # 	self.send_file(chatID, ret,message)
                except Exception:
                    self._logger.exception("Caught an exception trying send gif")
                    self.send_msg(
                        "Problem creating gif, please check log file and make sure you have installed libav-tools or ffmpeg",
                        chatID=chatID,
                    )
            else:
                self._logger.debug(f"Data so far: {data}")

                images_data_to_send = []
                r = None

                # Get thumbnail
                try:
                    if "thumbnail" in kwargs and kwargs["thumbnail"] is not None:
                        self._logger.debug(f"Get thumbnail: {kwargs['thumbnail']}")

                        url = f"http://localhost:{self.tcmd.port}/{kwargs['thumbnail']}"

                        r = requests.get(url, proxies=self.getProxies())
                        r.raise_for_status()

                        images_data_to_send.append(r.content)
                except Exception:
                    self._logger.exception("Exception occured on getting thumbnail")

                # Get images
                if with_image:
                    # Retrieve multicam profiles
                    multicam_profiles = None
                    try:
                        if self._plugin_manager.get_plugin(
                            "multicam", True
                        ) is not None and self._settings.get(["multicam"]):
                            self._logger.debug("Multicam detected")
                            multicam_profiles = self._settings.global_get(
                                ["plugins", "multicam", "multicam_profiles"]
                            )
                            self._logger.debug(
                                f"Multicam profiles: {multicam_profiles}"
                            )
                        else:
                            self._logger.debug("Multicam not detected")
                    except Exception:
                        self._logger.exception(
                            "Exception occured while getting multicam profiles"
                        )

                    # If there are multicam profiles, take images from them
                    if multicam_profiles:
                        for multicam_profile in multicam_profiles:
                            image_data = None

                            try:
                                image_data = self.take_image(
                                    multicam_profile.get("snapshot"),
                                    multicam_profile.get("flipH"),
                                    multicam_profile.get("flipV"),
                                    multicam_profile.get("rotate90"),
                                )
                            except Exception:
                                self._logger.exception(
                                    "Caught an exception trying taking an image"
                                )

                            if image_data:
                                images_data_to_send.append(image_data)
                            else:
                                message = f"[ERR GET IMAGE]\n\n{message}"

                    # If there aren't multicam profiles, fallback taking image from the octoprint default camera
                    else:
                        image_data = None

                        try:
                            image_data = self.take_image(
                                self._settings.global_get(["webcam", "snapshot"]),
                                self._settings.global_get(["webcam", "flipH"]),
                                self._settings.global_get(["webcam", "flipV"]),
                                self._settings.global_get(["webcam", "rotate90"]),
                            )
                        except Exception:
                            self._logger.exception(
                                "Caught an exception trying taking an image"
                            )

                        if image_data:
                            images_data_to_send.append(image_data)
                        else:
                            message = f"[ERR GET IMAGE]\n\n{message}"

                # Send message (with images, if there are)
                if len(images_data_to_send) == 1:
                    self._logger.debug(f"Sending with one image... ChatID: {chatID}")

                    if message != "":
                        data["caption"] = message

                    files = {"photo": ("image.jpg", images_data_to_send[0])}

                    r = requests.post(
                        f"{self.bot_url}/sendPhoto",
                        data=data,
                        files=files,
                        proxies=self.getProxies(),
                    )
                elif images_data_to_send:
                    self._logger.debug(
                        f"Sending with multiple images... ChatID: {chatID}"
                    )

                    files = {}
                    media = []

                    for i, image_data_to_send in enumerate(images_data_to_send):
                        files[f"photo_{i}"] = image_data_to_send

                        input_media_photo = {
                            "type": "photo",
                            "media": f"attach://photo_{i}",
                        }

                        if i == 0 and message != "":
                            input_media_photo["caption"] = message
                            
                        if message_data.get("parse_mode"):
                            input_media_photo["parse_mode"] = message_data["parse_mode"]

                        media.append(input_media_photo)

                    data["media"] = json.dumps(media)

                    r = requests.post(
                        f"{self.bot_url}/sendMediaGroup",
                        data=data,
                        files=files,
                        proxies=self.getProxies(),
                    )
                else:
                    self._logger.debug(f"Sending without images... ChatID: {chatID}")
                    data["text"] = message
                    r = requests.post(
                        f"{self.bot_url}/sendMessage",
                        data=data,
                        proxies=self.getProxies(),
                    )

                self._logger.debug(f"Sending finished. Status code: {r.status_code}")

                if r is not None and inline:
                    r.raise_for_status()
                    myJson = r.json()
                    if not myJson["ok"]:
                        raise NameError("ReqErr")
                    if "message_id" in myJson["result"]:
                        self.updateMessageID[chatID] = myJson["result"]["message_id"]

        except Exception:
            self._logger.exception("Caught an exception in _send_msg()")

        # PostImgMethod
        try:
            if with_image or with_gif:
                # TODO: Find a way to decide if should and what command to light on/off
                postmethod = self._settings.get(["PostImgMethod"])
                self._logger.debug(f"PostImgMethod {postmethod}")
                postcommand = self._settings.get(["PostImgCommand"])
                if postmethod == "GCODE":
                    self._logger.debug(f"PostImgCommand {postcommand}")
                    self._printer.commands(postcommand)
                    self._logger.debug("PostImg gcode command executed")
                elif postmethod == "SYSTEM":
                    self._logger.debug(f"PostImgCommand {postcommand}")
                    p = subprocess.Popen(postcommand, shell=True)
                    self._logger.debug(
                        f"PostImg system command executed. PID={p.pid}, Command={postcommand}"
                    )
                    while p.poll() is None:
                        time.sleep(0.1)
                        r = p.returncode
                        self._logger.debug(f"PostImg system command returned: {r}")
        except Exception:
            self._logger.exception("Exception PostImgMethod")

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

        try:
            requests.get(
                f"{self.bot_url}/sendChatAction",
                params={"chat_id": chat_id, "action": "upload_document"},
                proxies=self.getProxies(),
            )
            files = {"document": open(path, "rb")}
            r = requests.post(
                f"{self.bot_url}/sendDocument",
                files=files,
                data={"chat_id": chat_id, "caption": text},
                proxies=self.getProxies(),
            )
        except Exception:
            self._logger.exception("Caught an exception in send_file()")

    def send_editMessageMedia(self, chat_id, path, message_id):
        if not self.send_messages:
            return
        try:
            requests.get(
                f"{self.bot_url}/sendChatAction",
                params={"chat_id": chat_id, "action": "upload_document"},
                proxies=self.getProxies(),
            )
            files = {"document": open(path, "rb")}
            r = requests.post(
                f"{self.bot_url}/editMessageMedia",
                files=files,
                data={"chat_id": chat_id, "message_id": message_id},
                proxies=self.getProxies(),
            )
        except Exception:
            self._logger.exception("Caught an exception in send_editMessageMedia()")

    def delete_msg(self, chat_id, message_id):
        try:
            r = requests.post(
                f"{self.bot_url}/deleteMessage",
                data={"chat_id": chat_id, "message_id": message_id},
                proxies=self.getProxies(),
            )
        except Exception:
            self._logger.exception("Caught an exception in delete_msg()")

    def send_video(self, chatID, video_file, message):
        if not self.send_messages:
            return

        files = {"video": open(video_file, "rb")}
        r = requests.post(
            f"{self.bot_url}/sendVideo",
            files=files,
            data={"chat_id": chatID, "caption": message},
            proxies=self.getProxies(),
        )
        self._logger.debug(f"Sending finished. {r.status_code} {r.content}")

    def get_file(self, file_id):
        if not self.send_messages:
            return

        self._logger.debug(f"Requesting file with id {file_id}")
        r = requests.get(
            f"{self.bot_url}/getFile",
            data={"file_id": file_id},
            proxies=self.getProxies(),
        )
        r.raise_for_status()
        data = r.json()
        if not "ok" in data:
            raise Exception(
                f"Telegram didn't respond well to getFile. The response was: {r.text}"
            )
        url = f"{self.bot_file_url}/{data['result']['file_path']}"
        self._logger.debug(f"Downloading file: {url}")
        r = requests.get(url, proxies=self.getProxies())
        r.raise_for_status()
        return r.content

    def get_usrPic(self, chat_id, file_id=""):
        if not self.send_messages:
            return

        self._logger.debug(f"Requesting Profile Photo for chat_id: {chat_id}")
        try:
            if file_id == "":
                if int(chat_id) < 0:
                    self._logger.debug(
                        f"Not able to load group photos. Chat_id: {chat_id}. EXIT"
                    )
                    return
                self._logger.debug(f"requests.get({self.bot_url}/getUserProfilePhotos")
                r = requests.get(
                    f"{self.bot_url}/getUserProfilePhotos",
                    params={"limit": 1, "user_id": chat_id},
                    proxies=self.getProxies(),
                )
                r.raise_for_status()
                data = r.json()
                if not "ok" in data:
                    raise Exception(
                        f"Telegram didn't respond well to getUserProfilePhoto. Chat id: {chat_id}. The response was: {r.text}."
                    )
                if data["result"]["total_count"] < 1:
                    self._logger.debug(f"NO PHOTOS. CHAT ID: {chat_id}. EXIT.")
                    return
                r = self.get_file(data["result"]["photos"][0][0]["file_id"])
            else:
                r = self.get_file(file_id)
            file_name = os.path.join(
                self.get_plugin_data_folder(),
                "img",
                "user",
                os.path.basename(f"pic{chat_id}.jpg"),
            )
            img = Image.open(bytes_reader_class(r))
            img = img.resize((40, 40), Image.ANTIALIAS)
            img.save(file_name, format="JPEG")
            self._logger.info(f"Saved Photo. Chat id: {chat_id}")

        except Exception:
            self._logger.exception("Can't load UserImage")

    def test_token(self, token=None):
        if not self.send_messages:
            return

        if token is None:
            token = self._settings.get(["token"])
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe", proxies=self.getProxies()
        )
        self._logger.debug(f"getMe returned: {response.json()}")
        self._logger.debug(f"getMe status code: {response.status_code}")
        json = response.json()
        if not "ok" in json or not json["ok"]:
            if json["description"]:
                raise Exception
            else:
                raise Exception
        else:
            return f"@{json['result']['username']}"

    # Sets bot own list of commands
    def setMyCommands(self, force=False):
        if not self.send_messages:
            return
        try:
            shallRun = force
            if not force:
                # Check if a list of commands was already set
                resp = requests.get(
                    f"{self.bot_url}/getMyCommands", proxies=self.getProxies()
                ).json()
                self._logger.debug(f"getMyCommands returned {resp}")
                shallRun = len(resp["result"]) == 0
            if shallRun:
                commands = []
                commands.append(
                    {
                        "command": "status",
                        "description": "Displays the current status including a capture from the camera",
                    }
                )
                commands.append(
                    {
                        "command": "togglepause",
                        "description": "Pauses/Resumes current print",
                    }
                )
                commands.append(
                    {
                        "command": "home",
                        "description": "Home the printer print head",
                    }
                )
                commands.append(
                    {
                        "command": "files",
                        "description": "Lists all the files available for printing",
                    }
                )
                commands.append(
                    {
                        "command": "print",
                        "description": "Lets you start a print (confirmation required)",
                    }
                )
                commands.append(
                    {
                        "command": "tune",
                        "description": "Sets feed and flow rate, control temperatures",
                    }
                )
                commands.append(
                    {
                        "command": "ctrl",
                        "description": "Activates self defined controls from Octoprint",
                    }
                )
                commands.append(
                    {
                        "command": "con",
                        "description": "Connects or disconnects the printer",
                    }
                )
                commands.append(
                    {
                        "command": "sys",
                        "description": "Executes Octoprint system commands",
                    }
                )
                commands.append(
                    {
                        "command": "abort",
                        "description": "Aborts the currently running print (confirmation required)",
                    }
                )
                commands.append(
                    {"command": "off", "description": "Turn off the printer"}
                )
                commands.append({"command": "on", "description": "Turn on the printer"})
                commands.append(
                    {
                        "command": "settings",
                        "description": "Displays notification settings and lets change them",
                    }
                )
                commands.append(
                    {
                        "command": "upload",
                        "description": "Stores a file into the Octoprint library",
                    }
                )
                commands.append(
                    {
                        "command": "filament",
                        "description": "Shows filament spools and lets you change it (requires Filament Manager Plugin)",
                    }
                )
                commands.append({"command": "user", "description": "Gets user info"})
                commands.append(
                    {
                        "command": "gcode",
                        "description": "Call gCode commande with /gcode_XXX where XXX is the gcode command",
                    }
                )
                commands.append(
                    {
                        "command": "gif",
                        "description": "Sends a gif from the current video",
                    }
                )
                commands.append(
                    {
                        "command": "supergif",
                        "description": "Sends a bigger gif from the current video",
                    }
                )
                commands.append(
                    {
                        "command": "shutup",
                        "description": "Disables automatic notifications until the next print ends",
                    }
                )
                commands.append(
                    {
                        "command": "dontshutup",
                        "description": "Makes the bot talk again (opposite of `/shutup`)",
                    }
                )
                commands.append(
                    {"command": "help", "description": "Shows this help message"}
                )
                resp = requests.post(
                    f"{self.bot_url}/setMyCommands",
                    data={"commands": json.dumps(commands)},
                    proxies=self.getProxies(),
                ).json()
                self._logger.debug(f"setMyCommands returned {resp}")
        except Exception:
            pass

    def getProxies(self):
        http_proxy = self._settings.get(["http_proxy"])
        https_proxy = self._settings.get(["https_proxy"])
        return {"http": http_proxy, "https": https_proxy}

    ##########
    ### Helper methods
    ##########

    def str2bool(self, v):
        return v.lower() in ("yes", "true", "t", "1")

    # Checks if the received command is allowed to execute by the user
    def isCommandAllowed(self, chat_id, from_id, command):
        if "bind_none" in self.tcmd.commandDict[command]:
            return True
        if command is not None or command != "":
            if self.chats[chat_id]["accept_commands"]:
                if self.chats[chat_id]["commands"][command]:
                    return True
                elif int(chat_id) < 0 and self.chats[chat_id]["allow_users"]:
                    if (
                        self.chats[from_id]["commands"][command]
                        and self.chats[from_id]["accept_commands"]
                    ):
                        return True
            elif int(chat_id) < 0 and self.chats[chat_id]["allow_users"]:
                if (
                    self.chats[from_id]["commands"][command]
                    and self.chats[from_id]["accept_commands"]
                ):
                    return True
        return False

    # Helper function to handle /editMessageText Telegram API commands
    # See main._send_edit_msg()
    def getUpdateMsgId(self, id):
        uMsgID = ""
        if id in self.updateMessageID:
            uMsgID = self.updateMessageID[id]
            del self.updateMessageID[id]
        return uMsgID

    def take_image(self, snapshot_url="", flipH=False, flipV=False, rotate=False):
        if snapshot_url == "":
            snapshot_url = self._settings.global_get(["webcam", "snapshot"])

        snapshot_url = urljoin("http://localhost/", snapshot_url)

        self._logger.debug(f"Snapshot URL: {snapshot_url}")
        data = None

        if snapshot_url:
            try:
                r = requests.get(snapshot_url, timeout=10, proxies=self.getProxies())
                r.raise_for_status()
                data = r.content
            except Exception:
                self._logger.exception("Exception taking image")
                return None

        if data is None:
            return None

        self._logger.debug(f"Image transformations [H:{flipH}, V:{flipV}, R:{rotate}]")
        if flipH or flipV or rotate:
            image = Image.open(bytes_reader_class(data))
            if flipH:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            if flipV:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            if rotate:
                image = image.transpose(Image.ROTATE_90)
            output = bytes_reader_class()
            image.save(output, format="JPEG")
            data = output.getvalue()
            output.close()

        return data

    def get_current_layers(self):
        layers = None
        try:
            self._logger.debug(
                f"get_current_layers api key={self._settings.global_get(['api', 'key'])}"
            )
            if self._plugin_manager.get_plugin("DisplayLayerProgress", True):
                headers = {
                    "X-Api-Key": self._settings.global_get(["api", "key"]),
                }
                r = requests.get(
                    f"http://localhost:{int(self.tcmd.port)}/plugin/DisplayLayerProgress/values",
                    headers=headers,
                    timeout=3,
                    proxies=self.getProxies(),
                )
                self._logger.debug(f"get_current_layers : r={r}")
                if r.status_code >= 300:
                    return None
                else:
                    return r.json()
            else:
                return None
        except Exception:
            self._logger.exception(
                "An Exception in get layers from DisplayLayerProgress"
            )
        return layers

    def calculate_ETA(self, printTime=0):
        try:
            currentData = self._printer.get_current_data()
            current_time = datetime.datetime.today()
            if not currentData["progress"]["printTimeLeft"]:
                if printTime == 0:
                    return ""  # Maybe put something like "nothing to print" in here
                self._logger.debug(f"printTime={printTime}")
                try:
                    finish_time = current_time + datetime.timedelta(0, printTime)
                except Exception:
                    return ""
            else:
                finish_time = current_time + datetime.timedelta(
                    0, currentData["progress"]["printTimeLeft"]
                )

            if (
                finish_time.day > current_time.day
                and finish_time > current_time + datetime.timedelta(days=7)
            ):
                # Longer than a week ahead
                format = self._settings.get(["WeekTimeFormat"])  # "%d.%m.%Y %H:%M:%S"
            elif finish_time.day > current_time.day:
                # Not today but within a week
                format = self._settings.get(["DayTimeFormat"])  # "%a %H:%M:%S"
            else:
                # Today
                format = self._settings.get(["TimeFormat"])  # "%H:%M:%S"
            return finish_time.strftime(format)
        except Exception:
            self._logger.exception("Caught an Exception in get final time")
            return "There was a problem calculating the finishing time. Check the logs for more detail."

    def create_gif_new(self, chatID, sec=7, multicam_prof=None):
        ret = ""
        stream_url = 0
        if multicam_prof:
            stream_url = multicam_prof.get("URL")

        try:
            try:
                requests.get(
                    f"{self.bot_url}/sendChatAction",
                    params={"chat_id": chatID, "action": "record_video"},
                    proxies=self.getProxies(),
                )
            except Exception:
                self._logger.exception(
                    "Caught an exception trying sending action:record_video"
                )
            # 	saveDir = os.getcwd()
            # 	os.chdir(os.path.join(self.get_plugin_data_folder(), "tmpgif"))

            if multicam_prof:
                gif_basename = os.path.basename(
                    f"gif_{multicam_prof.get('name','').replace(' ', '_')}.mp4"
                )
                outPath = os.path.join(
                    self.get_plugin_data_folder(), "tmpgif", gif_basename
                )
            else:
                outPath = os.path.join(
                    self.get_plugin_data_folder(), "tmpgif", "gif.mp4"
                )

            self._logger.info(f"Removing file {outPath}")
            try:
                os.remove(outPath)
            except Exception:
                pass

            params = []
            self._logger.info("test if nice exist")
            if self.TestProgram(["nice", "--version"]) > 0:
                params = ["nice", "-n", "20"]

            self._logger.info("test if cpulimit exist")
            if self.TestProgram(["cpulimit", "--help"]) <= 0:
                self._logger.info(
                    "cpulimit don't exist so send a message to install and exit"
                )
                self.send_msg(
                    f"{self.gEmo('dizzy face')} Problem creating gif, please check log file, and make sure you have installed cpulimit with following command : `sudo apt-get install cpulimit`",
                    chatID=chatID,
                )
                return ""

            self._logger.info("test if ffmpeg exist")
            if self.TestProgram(["ffmpeg", "-h"]) <= 0:
                self._logger.info(
                    "ffmpeg don't exist so send a message to install and exit"
                )
                self.send_msg(
                    f"{self.gEmo('dizzy face')} Problem creating gif, please check log file, and make sure you have installed ffmpeg with following command : `sudo apt-get install ffmpeg`",
                    chatID=chatID,
                )
                return ""

            try:
                requests.get(
                    f"{self.bot_url}/sendChatAction",
                    params={"chat_id": chatID, "action": "record_video"},
                    proxies=self.getProxies(),
                )
            except Exception:
                self._logger.exception(
                    "Caught an exception trying sending action:record_video"
                )
            # os.nice(20) # Force this to use less CPU

            if stream_url == 0:
                stream_url = self._settings.global_get(["webcam", "stream"])

            stream_url = urljoin("http://localhost/", stream_url)

            if sec == 0:
                sec = 5  # int(self._settings.get(["number_img_gif"]))
            elif sec > 60:
                sec = 60
            elif sec < 1:
                sec = 1

            self._logger.info(f"sec={sec}")
            # timeSec = str(datetime.timedelta(seconds=sec))
            # self._logger.info("timeSec="+timeSec)
            timeSec = f"00:00:{sec:02d}"

            self._logger.info(f"timeSec={timeSec}")
            # timout = 4*sec
            # ffmpeg -i http://192.168.1.56/webcam/?action=stream -t 00:00:05 -vf scale=320x240 -y  -c:a copy out.mkv
            # params = ['ffmpeg', '-y', '-i' ,stream_url, '-t', "00:00:05",'-c:v','copy', '-c:a' ,'copy']
            used_cpu = 1
            limit_cpu = 65

            try:
                nb_cpu = multiprocessing.cpu_count()
                if nb_cpu > 1:
                    used_cpu = nb_cpu / 2
                    limit_cpu = 65 * used_cpu
            except Exception:
                self._logger.exception(
                    "Caught an exception trying to get number of cpu"
                )

            self._logger.info(
                f"limit_cpu={limit_cpu} | used_cpu={used_cpu} | because nb_cpu={nb_cpu}"
            )
            params.append("cpulimit")
            params.append("-l")
            params.append(str(limit_cpu))
            params.append("-f")
            params.append("-z")
            params.append("--")
            params.append("ffmpeg")
            params.append("-y")
            params.append("-threads")
            params.append(str(used_cpu))
            params.append("-i")
            params.append(stream_url)
            params.append("-t")
            params.append(timeSec)
            params.append("-pix_fmt")
            params.append("yuv420p")
            # Work on android but seems to be a problem on some Iphone
            # params.append( '-c:v')
            # params.append( 'mpeg4')
            # params.append(  '-c:a' )
            # params.append( 'mpeg4')
            # Works on iphone but seems to be a problem on some android
            # params.append( '-b:v')
            # params.append( '0')
            # params.append( '-crf')
            # params.append( '25')
            # params.append( '-movflags')
            # params.append( 'faststart')

            if multicam_prof != 0:
                flipH = multicam_prof.get("flipH")
                flipV = multicam_prof.get("flipV")
                rotate = multicam_prof.get("rotate90")
            else:
                flipH = self._settings.global_get(["webcam", "flipH"])
                flipV = self._settings.global_get(["webcam", "flipV"])
                rotate = self._settings.global_get(["webcam", "rotate90"])

            # Rotation
            flipping = ""
            if flipH or flipV or rotate:
                self._logger.info(
                    f"Image transformations [H:{flipH}, V:{flipV}, R:{rotate}]"
                )
                params.append("-vf")
                flipping = ""
                if flipV:
                    self._logger.info("Need flip vertical")
                    flipping += ",vflip"
                if flipH:
                    self._logger.info("Need flip horizontal")
                    flipping += ",hflip"
                if rotate:
                    self._logger.info("Need to rotate 90deg counter clockwise")
                    flipping += ",transpose=2"
                flipping = flipping.lstrip(",")
                params.append(flipping)

            # End Rotation

            # if (str(self._settings.get(["scale_gif"])) == "0"):#scale_gif
            # 	scale = ""
            # 	scale_opt =""
            # else:
            # 	params.append( "-vf")
            # 	params.append(f"scale={self._settings.get(['scale_gif'])})

            params.append(outPath)

            self._logger.info(f"will now create the video {str(params).strip('[]')}")
            try:
                requests.get(
                    f"{self.bot_url}/sendChatAction",
                    params={"chat_id": chatID, "action": "record_video"},
                    proxies=self.getProxies(),
                )
            except Exception:
                self._logger.exception(
                    "Caught an exception trying sending action:record_video"
                )

            myproc = subprocess.Popen(
                params, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            while True:
                if myproc.poll() is not None:
                    break
                try:
                    requests.get(
                        f"{self.bot_url}/sendChatAction",
                        params={"chat_id": chatID, "action": "record_video"},
                        proxies=self.getProxies(),
                    )
                except Exception:
                    self._logger.exception(
                        "Caught an exception trying sending action:record_video"
                    )
                time.sleep(0.5)

            self._logger.info("Finish the video")
            try:
                requests.get(
                    f"{self.bot_url}/sendChatAction",
                    params={"chat_id": chatID, "action": "record_video"},
                    proxies=self.getProxies(),
                )
            except Exception:
                self._logger.exception(
                    "Caught an exception trying sending action:record_video"
                )
            ret = outPath
        except Exception:
            self._logger.exception(
                "Caught an exception trying create gif general error"
            )
            self.send_msg(
                f"{self.gEmo('dizzy face')} Problem creating gif, please check log file",
                chatID=chatID,
            )
            ret = ""

        # os.nice(0) # Use CPU usage to default
        return ret

    def TestProgram(self, name):
        try:
            self._logger.info(f"Test exist program {str(name).strip('[]')}")
            # Pipe output to /dev/null for silence
            ret = subprocess.call(name)
            self._logger.info(f"ret = {ret}")
            return ret >= 0

        except OSError:
            return -1

    def route_hook(self, server_routes, *args, **kwargs):
        from octoprint.server.util.tornado import LargeResponseHandler

        os.makedirs(
            os.path.join(self.get_plugin_data_folder(), "img", "user"), exist_ok=True
        )
        os.makedirs(
            os.path.join(self.get_plugin_data_folder(), "tmpgif"), exist_ok=True
        )

        return [
            (
                r"/img/user/(.*)",
                LargeResponseHandler,
                dict(
                    path=os.path.join(self.get_plugin_data_folder(), "img", "user"),
                    allow_client_caching=False,
                ),
            ),
            (
                r"/static/img/(.*)",
                LargeResponseHandler,
                dict(
                    path=os.path.join(self._basefolder, "static", "img"),
                    allow_client_caching=True,
                ),
            ),
        ]

    # Function to be able to do action on gcode
    def hook_gcode_sent(
        self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs
    ):
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


########################################
########################################
### Some methods to check version and
### get the right implementation
########################################
########################################


# Copied from pluginmanager plugin
def _is_octoprint_compatible(compatibility_entries):
    """
    Tests if the current octoprint_version is compatible to any of the provided ``compatibility_entries``
    """

    octoprint_version = _get_octoprint_version()
    for octo_compat in compatibility_entries:
        if not any(
            octo_compat.startswith(c)
            for c in ("<", "<=", "!=", "==", ">=", ">", "~=", "===")
        ):
            octo_compat = f">={octo_compat}"

        s = next(pkg_resources.parse_requirements(f"OctoPrint{octo_compat}"))
        if octoprint_version in s:
            break
    else:
        return False

    return True


# Copied from pluginmanager plugin
def _get_octoprint_version():
    from octoprint.server import VERSION

    octoprint_version_string = VERSION

    if "-" in octoprint_version_string:
        octoprint_version_string = octoprint_version_string[
            : octoprint_version_string.find("-")
        ]

    octoprint_version = pkg_resources.parse_version(octoprint_version_string)
    if isinstance(octoprint_version, tuple):
        # Old setuptools
        base_version = []
        for part in octoprint_version:
            if part.startswith("*"):
                break
            base_version.append(part)
        octoprint_version = ".".join(base_version)
    else:
        # New setuptools
        octoprint_version = pkg_resources.parse_version(octoprint_version.base_version)

    return octoprint_version


# Check if we have min version 1.3.0.
# This is important because of WizardPlugin mixin and folders in filebrowser.
def get_implementation_class():
    if not _is_octoprint_compatible(["1.3.0"]):
        return TelegramPlugin(1.2)
    else:

        class NewTelegramPlugin(TelegramPlugin, octoprint.plugin.WizardPlugin):
            def __init__(self, version):
                super(NewTelegramPlugin, self).__init__(version)

        return NewTelegramPlugin(1.3)


__plugin_name__ = "Telegram Notifications"
__plugin_pythoncompat__ = ">=3.6,<4"
__plugin_implementation__ = get_implementation_class()
__plugin_hooks__ = {
    "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
    "octoprint.server.http.routes": __plugin_implementation__.route_hook,
    "octoprint.comm.protocol.gcode.received": __plugin_implementation__.recv_callback,
    "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.hook_gcode_sent,
}
