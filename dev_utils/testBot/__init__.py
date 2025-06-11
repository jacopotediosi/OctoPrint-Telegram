from __future__ import absolute_import
from PIL import Image
import threading, requests, re, time, datetime, StringIO, json, random, logging, traceback, io, collections, os, base64, PIL
from telegramCommands import TCMD  # telegramCommands.
from telegramNotifications import TMSG  # telegramNotifications
from telegramNotifications import telegramMsgDict  # dict of known notification messages
from emojiDict import telegramEmojiDict  # dict of known emojis
from users import settingsDict

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
        self.gEmo = self.main.gEmo

    def run(self):
        print "Try first connect."
        self.try_first_contact()
        # repeat fetching and processing messages unitil thread stopped
        print "Listener is running."
        try:
            while not self.do_stop:
                try:
                    self.loop()
                except ExitThisLoopException:
                    # do nothing, just go to the next loop
                    pass
        except Exception as ex:
            print "An Exception crashed the Listener: " + str(
                ex
            ) + " Traceback: " + traceback.format_exc()

        print "Listener exits NOW."

    # Try to get first contact. Repeat every 120sek if no success
    # or stop if task stopped
    def try_first_contact(self):
        gotContact = False
        while not self.do_stop and not gotContact:
            try:
                self.username = self.main.test_token()
                gotContact = True
                self.set_status("Connected as" + self.username + ".", ok=True)
            except Exception as ex:
                self.set_status(
                    "Got an exception while initially trying to connect to telegram (Listener not running: "
                    + ex
                    + ".  Waiting 2 minutes before trying again.)"
                )
                time.sleep(120)

    def loop(self):
        chat_id = ""
        json = self.get_updates()

        try:
            # seems like we got a message, so lets process it.
            for message in json["result"]:
                self.process_message(message)
        except ExitThisLoopException as exit:
            raise exit
        # wooooops. can't handle the message
        except Exception as ex:
            print "Exception caught! " + str(ex)

        self.set_status("Connected as " + self.username + ".", ok=True)
        # we had first contact after octoprint startup
        # so lets send startup message
        if self.first_contact:
            self.first_contact = False
            self.main.on_event("PrinterStart", {})

    def process_message(self, message):
        print "MESSAGE: " + str(message)
        # Get the update_id to only request newer Messages the next time
        if message["update_id"] >= self.update_offset:
            self.update_offset = message["update_id"] + 1
        # no message no cookies
        if "message" in message and message["message"]["chat"]:
            chat_id, from_id = self.parse_user_data(message)
            # if we come here without a continue (discard message)
            # we have a message from a known and not new user
            # so let's check what he send us
            # if message is a text message, we probably got a command
            # if the command is not known, the following handler will discard it
            if "text" in message["message"]:
                self.handle_text_message(message, chat_id, from_id)
            # we got no message with text (command) so lets check if we got a file
            # the following handler will check file and saves it to disk
            elif "document" in message["message"]:
                self.handle_document_message(message, chat_id, from_id)
            # we got message with notification for a new chat title photo
            # so lets download it
            elif "new_chat_photo" in message["message"]:
                self.handle_new_chat_photo_message(message, chat_id, from_id)
            # we got message with notification for a deleted chat title photo
            # so we do the same
            elif "delete_chat_photo" in message["message"]:
                self.handle_delete_chat_photo_message(message, chat_id, from_id)
            # a member was removed from a group, so lets check if it's our bot and
            # delete the group from our chats if it is our bot
            elif "left_chat_member" in message["message"]:
                self.handle_left_chat_member_message(message, chat_id, from_id)
            # we are at the end. At this point we don't know what message type it is, so we do nothing
            else:
                print "Got an unknown message. Doing nothing. Data: " + str(message)
        elif "callback_query" in message:
            self.handle_callback_query(message)
        else:
            print "Response is missing .message or .message.chat or .callback_query.Skipping it."
            raise ExitThisLoopException()

    def handle_callback_query(self, message):
        print "IN CALLBACK"
        message["callback_query"]["message"]["reply_to_message"]["text"] = message[
            "callback_query"
        ]["data"]
        chat_id, from_id = self.parse_user_data(message["callback_query"])
        self.handle_text_message(message["callback_query"], chat_id, from_id)

    def handle_left_chat_member_message(self, message, chat_id, from_id):
        print "Message Del_Chat"
        if (
            message["message"]["left_chat_member"]["username"] == self.username[1:]
            and str(message["message"]["chat"]["id"]) in self.main.chats
        ):
            del self.main.chats[str(message["message"]["chat"]["id"])]
            # do a self._settings.save() ???
            print "Chat deleted"

    def handle_delete_chat_photo_message(self, message, chat_id, from_id):
        print "Message Del_Chat_Photo"
        try:
            # os.remove(self.main.get_plugin_data_folder()+"/img/user/pic" +str(message['message']['chat']['id'])+".jpg")
            print "File removed"
        except OSError:
            pass

    def handle_new_chat_photo_message(self, message, chat_id, from_id):
        print "Message New_Chat_Photo"
        # only if we know the chat
        if str(message["message"]["chat"]["id"]) in self.main.chats:
            print "New_Chat_Photo Found User"
            kwargs = {
                "chat_id": int(message["message"]["chat"]["id"]),
                "file_id": message["message"]["new_chat_photo"][0]["file_id"],
            }
            t = threading.Thread(target=self.main.get_usrPic, kwargs=kwargs)
            t.daemon = True
            t.run()

    def handle_document_message(self, message, chat_id, from_id):
        # first we have to check if chat or group is allowed to upload
        from_id = chat_id
        if not self.main.chats[chat_id][
            "private"
        ]:  # is this needed? can one send files from groups to bots?
            from_id = str(message["message"]["from"]["id"])
        # is /upload allowed?
        if self.is_command_allowed(chat_id, from_id, "/upload"):
            try:
                file_name = message["message"]["document"]["file_name"]
                if not (
                    file_name.lower().endswith(".gcode")
                    or file_name.lower().endswith(".gco")
                    or file_name.lower().endswith(".g")
                ):
                    self.main.send_msg(
                        self.gEmo("warning")
                        + " Sorry, I only accept files with .gcode, .gco or .g extension.",
                        chatID=chat_id,
                    )
                    raise ExitThisLoopException()
                # download the file
                target_filename = "telegram_" + file_name
                # for parameter no_markup see _send_edit_msg()
                self.main.send_msg(
                    (self.gEmo("save") + " Saving file {}...".format(target_filename)),
                    chatID=chat_id,
                    noMarkup=True,
                )
                requests.get(
                    self.main.bot_url + "/sendChatAction",
                    params={"chat_id": chat_id, "action": "upload_document"},
                )
                data = self.main.get_file(message["message"]["document"]["file_id"])
                # stream = octoprint.filemanager.util.StreamWrapper(file_name, io.BytesIO(data))
                # self.main._file_manager.add_file(octoprint.filemanager.FileDestinations.LOCAL, target_filename, stream, allow_overwrite=True)
                # for parameter msg_id see _send_edit_msg()
                self.main.send_msg(
                    self.gEmo("upload")
                    + " I've successfully saved the file you sent me as {}.".format(
                        target_filename
                    ),
                    msg_id=self.get_update_msg_id(chat_id),
                    chatID=chat_id,
                )
            except Exception as ex:
                self.main.send_msg(
                    self.gEmo("warning")
                    + " Something went wrong during processing of your file."
                    + self.gEmo("mistake")
                    + " Sorry. More details are in octoprint.log.",
                    msg_id=self.get_update_msg_id(chat_id),
                    chatID=chat_id,
                )
                print "Exception occured during processing of a file: " + traceback.format_exc()
        else:
            print "Previous file was from an unauthorized user."
            self.main.send_msg(
                "Don't feed the octopuses! " + self.gEmo("octo"), chatID=chat_id
            )

    def handle_text_message(self, message, chat_id, from_id):
        # We got a chat message.
        # handle special messages from groups (/commad@BotName)
        command = message["message"]["text"].split("@")[0]
        # reply_to_messages will be send on value inputs (eg notification height)
        # but also on android when pushing a button. Then we have to switch command and parameter.
        parameter = ""
        if (
            "reply_to_message" in message["message"]
            and "text" in message["message"]["reply_to_message"]
        ):
            command = message["message"]["reply_to_message"]["text"]
            parameter = message["message"]["text"]
            print command.encode("utf-8")
            if command.encode("utf-8") not in [
                str(k.encode("utf-8")) for k in self.main.tcmd.commandDict.keys()
            ]:
                print "IN IF"
                command = message["message"]["text"]
                parameter = message["message"]["reply_to_message"]["text"]
        # if command is '/print_', '/sys_' or '/ctrl_', get the parameter
        elif "/print_" in command or "/sys_" in command or "/ctrl_" in command:
            parameter = "_".join(command.split("_")[1:])
            command = command.split("_")[0] + "_"
        print "DONE"
        print "Got a command: '" + str(
            command.encode("utf-8")
        ) + "' with parameter: '" + str(parameter.encode("utf-8")) + "' in chat " + str(
            message["message"]["chat"]["id"]
        )
        # is command  known?
        if command not in self.main.tcmd.commandDict:
            # we dont know the command so skip the message
            print "Previous command was an unknown command."
            self.main.send_msg(
                "I do not understand you! " + self.gEmo("mistake"), chatID=chat_id
            )
            raise ExitThisLoopException()
        # check if user is allowed to execute the command
        if self.is_command_allowed(
            chat_id, from_id, command
        ) and self.main.tcmd.checkState(from_id, command, parameter):
            # messageRespondID is needed to send command replys only to the sender
            # if message is from a group
            self.main.messageResponseID = message["message"]["message_id"]
            # execute command
            self.main.tcmd.commandDict[command]["cmd"](
                chat_id=chat_id, parameter=parameter, cmd=command
            )
            # we dont need the messageResponseID anymore
            self.main.messageResponseID = None
        else:
            # user was not alloed to execute this command
            print "Previous command was from an unauthorized user."
            self.main.send_msg(
                "You are not allowed to do this! " + self.gEmo("notallowed"),
                chatID=chat_id,
            )

    def parse_user_data(self, message):
        self.main.chats = self.main._settings["chats"]
        chat = message["message"]["chat"]
        chat_id = str(chat["id"])
        data = self.main.newChat  # data for new user
        # if we know the user or chat, overwrite data with user data
        if chat_id in self.main.chats:
            data = self.main.chats[chat_id]
        # update data or get data for new user
        if chat["type"] == "group":
            data["private"] = False
            data["title"] = chat["title"]
        elif chat["type"] == "private":
            data["private"] = True
            data["title"] = ""
            if "first_name" in chat:
                data["title"] += chat["first_name"] + " - "
            if "last_name" in chat:
                data["title"] += chat["last_name"] + " - "
            if "username" in chat:
                data["title"] += "@" + chat["username"]
        from_id = chat_id
        # if message is from a group, chat_id will be left as id of group
        # and from_id is set to id of user who send the message
        if not data["private"]:
            from_id = str(message["message"]["from"]["id"])
            # if group accepts only commands from known users (allow_users = true, accept_commands=false)
            # and user is not in known chats, then he is unknown and we dont want to listen to him.
            if chat_id in self.main.chats:
                if (
                    self.main.chats[chat_id]["allow_users"]
                    and from_id not in self.main.chats
                    and not self.main.chats[chat_id]["accept_commands"]
                ):
                    print "Previous command was from an unknown user."
                    self.main.send_msg(
                        "I don't know you! Certainly you are a nice Person "
                        + self.gEmo("heart"),
                        chatID=chat_id,
                    )
                    raise ExitThisLoopException()
        # if we dont know the user or group, create new user
        # send welcome message and skip message
        if chat_id not in self.main.chats:
            self.main.chats[chat_id] = data
            self.main.send_msg(
                self.gEmo("info")
                + "Now i know you. Before you can do anything, go to OctoPrint Settings and edit some rights.",
                chatID=chat_id,
            )
            kwargs = {"chat_id": int(chat_id)}
            t = threading.Thread(target=self.main.get_usrPic, kwargs=kwargs)
            t.daemon = True
            t.run()
            print "Got new User"
            raise ExitThisLoopException()
        # if octoprint just started we only check connection. so discard messages
        # we do this on end of this function. so we don't miss a new user who tried to
        # pair with the bot when printer was offline.
        if self.first_contact:
            print "Ignoring message because first_contact is True."
            raise ExitThisLoopException()
        return (chat_id, from_id)

    def get_updates(self):
        print "listener: sending request with offset " + str(self.update_offset) + "..."
        req = None

        # try to check for incoming messages. wait 120sek and repeat on failure
        try:
            timeout = 30
            if self.update_offset == 0 and self.first_contact:
                timeout = 0
                self.update_offset = 1
            req = requests.get(
                f"{self.main.bot_url}/getUpdates",
                params={"offset": self.update_offset, "timeout": timeout},
                allow_redirects=False,
                timeout=timeout + 10,
            )
        except requests.exceptions.Timeout:
            # Just start the next loop.
            raise ExitThisLoopException()
        except Exception as ex:
            self.set_status(
                "Got an exception while trying to connect to telegram API: "
                + str(ex)
                + ". Waiting 2 minutes before trying again."
            )
            time.sleep(120)
            raise ExitThisLoopException()
        if req.status_code != 200:
            self.set_status(
                "Telegram API responded with code "
                + str(req.status_code)
                + ". Waiting 2 minutes before trying again."
            )
            time.sleep(120)
            raise ExitThisLoopException()
        if req.headers["content-type"] != "application/json":
            self.set_status(
                "Unexpected Content-Type. Expected: application/json. Was: "
                + str(req.headers["content-type"])
                + " Waiting 2 minutes before trying again."
            )
            time.sleep(120)
            raise ExitThisLoopException()
        json = req.json()
        if not json["ok"]:
            self.set_status(
                "Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: "
                + str(json)
            )
            time.sleep(120)
            raise ExitThisLoopException()
        return json

    # checks if the received command is allowed to execute by the user
    def is_command_allowed(self, chat_id, from_id, command):
        if command is not None or command is not "":
            if self.main.chats[chat_id]["accept_commands"]:
                if self.main.chats[chat_id]["commands"][command]:
                    return True
                elif int(chat_id) < 0 and self.main.chats[chat_id]["allow_users"]:
                    if (
                        self.main.chats[from_id]["commands"][command]
                        and self.main.chats[from_id]["accept_commands"]
                    ):
                        return True
            elif int(chat_id) < 0 and self.main.chats[chat_id]["allow_users"]:
                if (
                    self.main.chats[from_id]["commands"][command]
                    and self.main.chats[from_id]["accept_commands"]
                ):
                    return True
        return False

    # Helper function to handle /editMessageText Telegram API commands
    # see main._send_edit_msg()
    def get_update_msg_id(self, id):
        uMsgID = None
        if id in self.main.updateMessageID:
            uMsgID = self.main.updateMessageID[id]
            del self.main.updateMessageID[id]
        return uMsgID

    # stop the listener
    def stop(self):
        self.do_stop = True

    def set_status(self, status, ok=False):
        if status != self.main.connection_state_str:
            if self.do_stop:
                print "Would set status but do_stop is True: %s", status
                return
            if ok:
                print "Setting status: %s", status
            else:
                print "Setting status: %s", status
        self.connection_ok = ok
        self.main.connection_state_str = status


class ExitThisLoopException(Exception):
    pass


########################################
########################################
############## THE PLUGIN ##############
########################################
########################################


class TelegramPlugin:
    def __init__(self):
        # for more init stuff see on_after_startup()
        self.thread = None
        self._settings = settingsDict.copy()
        self.bot_url = None
        self.connection_state_str = "Disconnected."
        self.connection_ok = False
        self.messageResponseID = None
        requests.packages.urllib3.disable_warnings()
        self.updateMessageID = {}
        self.shut_up = {}
        # use of emojis see below at method gEmo()
        self.emojis = {
            "octo": "\U0001F419",  # octopus
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
        # initial settings for new chat. See on_after_startup()
        # !!! sync with newUsrDict in on_settings_migrate() !!!
        self.tcmd = TCMD(self)
        self.tmsg = TMSG(self)
        self.newChat = {
            "private": True,
            "title": "[UNKNOWN]",
            "accept_commands": False,
            "send_notifications": False,
            "new": True,
            "allow_users": False,
            "commands": {k: False for k, v in self.tcmd.commandDict.iteritems()},
            "notifications": {k: False for k, v in telegramMsgDict.iteritems()},
        }

        iterItems = settingsDict["chats"].copy()
        for key in iterItems:
            data = settingsDict["chats"][key].copy()
            if "commands" in data:
                for cmd in self.tcmd.commandDict:
                    if not cmd in data["commands"]:
                        data["commands"].update({cmd: True})
            else:
                data["commands"] = {
                    k: True for k, v in self.tcmd.commandDict.iteritems()
                }
            if "notifications" in data:
                for cmd in telegramMsgDict:
                    if not cmd in data["notifications"]:
                        data["notifications"].update({cmd: True})
            else:
                data["notifications"] = {
                    k: True for k, v in telegramMsgDict.iteritems()
                }
            settingsDict["chats"][key] = data
        self.chats = self._settings["chats"]
        self.start_listening()
        print str(self.chats)

    # all emojis will be get via this method to disable them globaly by the corrosponding setting
    # so if you want to use emojis anywhere use gEmo("...") istead of emojis["..."]
    def gEmo(self, key):
        return self.emojis[key]

    # starts the telegram listener thread
    def start_listening(self):
        if self._settings["token"] != "" and self.thread is None:
            print "Starting listener."
            self.bot_url = "https://api.telegram.org/bot" + self._settings["token"]
            self.bot_file_url = (
                "https://api.telegram.org/file/bot" + self._settings["token"]
            )
            self.thread = TelegramListener(self)
            self.thread.daemon = True
            self.thread.start()

    # stops the telegram listener thread
    def stop_listening(self):
        self.on_event("PrinterShutdown", {})
        if self.thread is not None:
            print "Stopping listener."
            self.thread.stop()
            self.thread = None

    ##########
    ### EventHandler API
    ##########

    def on_event(self, event, payload, **kwargs):
        try:
            # if we know the event, start handler
            if event in self.tmsg.msgCmdDict:
                print "Got an event: " + event + " Payload: " + str(payload)
                # Start event handler
                self.tmsg.startEvent(event, payload, **kwargs)
            else:
                # return as fast as possible
                return
        except Exception as e:
            print "Exception: " + str(e)

    ##########
    ### Telegram API-Functions
    ##########

    def send_msg(self, message, **kwargs):
        kwargs["message"] = message
        try:
            # If it's a regular event notification
            if "chatID" not in kwargs and "event" in kwargs:
                print "Send_msg() found event: " + str(kwargs["event"])
                for key in self.chats:
                    if key != "zBOTTOMOFCHATS":
                        if (
                            self.chats[key]["notifications"][kwargs["event"]]
                            and key not in self.shut_up
                            and self.chats[key]["send_notifications"]
                        ):
                            kwargs["chatID"] = key
                            t = threading.Thread(
                                target=self._send_msg, kwargs=kwargs
                            ).run()
            # Seems to be a broadcast
            elif "chatID" not in kwargs:
                for key in self.chats:
                    kwargs["chatID"] = key
                    t = threading.Thread(target=self._send_msg, kwargs=kwargs).run()
            # This is a 'editMessageText' message
            elif "msg_id" in kwargs:
                if kwargs["msg_id"] is not None:
                    t = threading.Thread(
                        target=self._send_edit_msg, kwargs=kwargs
                    ).run()
            # direct message or event notification to a chat_id
            else:
                t = threading.Thread(target=self._send_msg, kwargs=kwargs).run()
        except Exception as ex:
            print "Caught an exception in send_msg(): " + str(ex)

    # this method is used to update a message text of a sent message
    # the sent message had to have no_markup = true when calling send_msg() (otherwise it would not work)
    # by setting no_markup = true we got a messageg_id on sending the message which is saved in selfupdateMessageID
    # if this message_id is passed in msg_id to send_msg() then this method will be called
    def _send_edit_msg(
        self, message="", msg_id="", chatID="", force_reply=False, **kwargs
    ):
        try:
            print "Sending a message UPDATE: "  # + message.replace("\n", "\\n") + " chatID= " + str(chatID)
            data = {}
            data["text"] = message
            data["message_id"] = msg_id
            data["chat_id"] = int(chatID)
            print "SENDING UPDATE: " + str(data)
            req = requests.post(self.bot_url + "/editMessageText", data=data)
            if req.headers["content-type"] != "application/json":
                print "Unexpected Content-Type. Expected: application/json. Was: " + str(
                    req.headers["content-type"]
                ) + ". Waiting 2 minutes before trying again."
                return
            myJson = req.json()
            print "REQUEST RES: " + str(myJson)
        except Exception as ex:
            print "Caught an exception in _send_edit_msg(): " + str(ex)

    def _send_msg(
        self,
        message="",
        with_image=False,
        responses=None,
        force_reply=False,
        delay=0,
        noMarkup=False,
        chatID="",
        markup="",
        showWeb=False,
        **kwargs
    ):
        if delay > 0:
            time.sleep(delay)
        try:
            if with_image is None:
                with_image = False
            if with_image:
                if (
                    "event" in kwargs
                    and not self._settings["messages"][kwargs["event"]]["combined"]
                ):
                    args = locals()
                    # print "Sending seperated image message..."
                    # for key in args:
                    # print "Local: " + str(key) + " | " + str(args[key])
                    # if key is not "kwargs" and key is not "self":
                    # kwargs.update({key:args[key]})
                    del args["kwargs"]["event"]
                    del args["self"]
                    args["message"] = ""
                    print "Sending image..."
                    t = threading.Thread(target=self._send_msg, kwargs=args).run()
                    args["message"] = message
                    args["with_image"] = False
                    print "Sending text..."
                    t = threading.Thread(target=self._send_msg, kwargs=args).run()
                    return

            print "Sending a message: "  # + str(message.replace("\n", "\\n") )+ " with_image=" + str(with_image) + " chatID= " + str(chatID)
            data = {}
            # Do we want to show web link previews?
            data["disable_web_page_preview"] = not showWeb
            # We always send hide_keyboard unless we send an actual keyboard or an Message Update (noMarkup = true)
            if not noMarkup:
                data["reply_markup"] = json.dumps({"hide_keyboard": True})
            # Do we want the message to be parsed in any markup?
            if markup is not None:
                if "HTML" in markup or "Markdown" in markup:
                    data["parse_mode"] = markup
            if force_reply:
                if self.messageResponseID != None:
                    data["reply_markup"] = json.dumps(
                        {"force_reply": True, "selective": True}
                    )
                    data["reply_to_message_id"] = self.messageResponseID
                else:
                    data["reply_markup"] = json.dumps({"force_reply": True})
            if responses:
                if self.messageResponseID != None:
                    keyboard = {
                        "inline_keyboard": [
                            map(
                                lambda x: {"text": x[0], "callback_data": x[1]},
                                responses,
                            )
                        ]
                    }
                    data["reply_markup"] = json.dumps(keyboard)
                    data["reply_to_message_id"] = self.messageResponseID
                else:
                    keyboard = {
                        "inline_keyboard": [
                            map(
                                lambda x: {"text": x[0], "callback_data": x[1]},
                                responses,
                            )
                        ]
                    }
                    data["reply_markup"] = json.dumps(keyboard)

            image_data = None
            if with_image:
                image_data = self.take_image()
            print "data so far: " + str(data)

            if chatID in self.updateMessageID:
                del self.updateMessageID[chatID]

            r = None
            data["chat_id"] = chatID
            if image_data:
                print "Sending with image.. " + str(chatID)
                files = {"photo": ("image.jpg", image_data)}
                if message is not "":
                    data["caption"] = message
                r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data)
                print "Sending finished. " + str(r.status_code)
            else:
                print "Sending without image.. " + str(chatID)
                data["text"] = message
                r = requests.post(self.bot_url + "/sendMessage", data=data)
                print "Sending finished. " + str(r.status_code)
            if r is not None and noMarkup:
                r.raise_for_status()
                myJson = r.json()
                if not myJson["ok"]:
                    raise NameError("ReqErr")
                if "message_id" in myJson["result"]:
                    self.updateMessageID[chatID] = myJson["result"]["message_id"]
        except Exception as ex:
            print "Caught an exception in _send_msg(): " + str(ex)
        self.messageResponseID = None

    def send_video(self, message, video_file):
        files = {"video": open(video_file, "rb")}
        # r = requests.post(self.bot_url + "/sendVideo", files=files, data={'chat_id':self._settings["chat"]), 'caption':message})
        print "Sending finished. " + str(r.status_code) + " " + str(r.content)

    def get_file(self, file_id):
        print "Requesting file with id %s.", file_id
        r = requests.get(self.bot_url + "/getFile", data={"file_id": file_id})
        # {"ok":true,"result":{"file_id":"BQADAgADCgADrWJxCW_eFdzxDPpQAg","file_size":26,"file_path":"document\/file_3.gcode"}}
        r.raise_for_status()
        data = r.json()
        if not "ok" in data:
            raise Exception(
                _(
                    "Telegram didn't respond well to getFile. The response was: %(response)s",
                    response=r.text,
                )
            )
        url = self.bot_file_url + "/" + data["result"]["file_path"]
        print "Downloading file: %s", url
        r = requests.get(url)
        r.raise_for_status()
        return r.content

    def get_usrPic(self, chat_id, file_id=""):
        print "Requesting Profile Photo for chat_id: " + str(chat_id)
        try:
            if file_id == "":
                if int(chat_id) < 0:
                    print "Not able to load group photos. " + str(chat_id) + " EXIT"
                    return
                r = requests.get(
                    self.bot_url + "/getUserProfilePhotos",
                    params={"limit": 1, "user_id": chat_id},
                )
                r.raise_for_status()
                data = r.json()
                if not "ok" in data:
                    raise Exception(
                        _(
                            "Telegram didn't respond well to getUserProfilePhoto "
                            + str(chat_id)
                            + ". The response was: %(response)s",
                            response=r.text,
                        )
                    )
                if data["result"]["total_count"] < 1:
                    print "NO PHOTOS " + str(chat_id) + ". EXIT"
                    return
                r = self.get_file(data["result"]["photos"][0][0]["file_id"])
            else:
                r = self.get_file(file_id)
            # file_name = self.get_plugin_data_folder() + "/img/user/pic" + str(chat_id) + ".jpg"
            img = Image.open(StringIO.StringIO(r))
            img = img.resize((40, 40), PIL.Image.ANTIALIAS)
            # img.save(file_name, format="JPEG")
            print "Saved Photo " + str(chat_id)

        except Exception as ex:
            print "Can't load UserImage: " + str(ex)

    def test_token(self, token=None):
        if token is None:
            token = self._settings["token"]
        response = requests.get("https://api.telegram.org/bot" + token + "/getMe")
        print "getMe returned: " + str(response.json())
        print "getMe status code: " + str(response.status_code)
        json = response.json()
        if not "ok" in json or not json["ok"]:
            if json["description"]:
                raise (
                    Exception(
                        "Telegram returned error code %(error)s: %(message)s",
                        error=json["error_code"],
                        message=json["description"],
                    )
                )
            else:
                raise (Exception("Telegram returned an unspecified error."))
        else:
            return "@" + json["result"]["username"]

    ##########
    ### Helper methods
    ##########

    def str2bool(self, v):
        return v.lower() in ("yes", "true", "t", "1")

    def take_image(self):
        # snapshot_url = self._settings.global_get(["webcam", "snapshot"])
        # print "Snapshot URL: " + str(snapshot_url)
        data = None
        # if snapshot_url:
        # try:
        # r = requests.get(snapshot_url)
        # data = r.content
        # except Exception as e:
        # return None
        # flipH = self._settings.global_get(["webcam", "flipH"])
        # flipV = self._settings.global_get(["webcam", "flipV"])
        # rotate= self._settings.global_get(["webcam", "rotate90"])

        # if flipH or flipV or rotate:
        # image = Image.open(StringIO.StringIO(data))
        # if rotate:
        # image = image.transpose(Image.ROTATE_90)
        # if flipH:
        # image = image.transpose(Image.FLIP_LEFT_RIGHT)
        # if flipV:
        # image = image.transpose(Image.FLIP_TOP_BOTTOM)
        # output = StringIO.StringIO()
        # image.save(output, format="JPEG")
        # data = output.getvalue()
        # output.close()
        return data


listener = TelegramPlugin()
listener.start_listening()
i = 0
while 1:
    i += 1
