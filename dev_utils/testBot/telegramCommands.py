import hashlib

################################################################################################################
# This class handles received commands/messages (commands in the following). commandDict{} holds the commands and their behavior.
# Each command has its own handler. If you want to add/del commands, read the following:
# SEE DOCUMENTATION IN WIKI: https://github.com/jacopotediosi/OctoPrint-Telegram/wiki/Add%20commands%20and%20notifications
#####################################################################################################################


class TCMD:
    def __init__(self, main):
        self.main = main
        self.main.gEmo = self.main.gEmo
        self.stateList = {}
        self.commandDict = {
            "Yes": {"cmd": self.cmdYes, "bind_none": True},
            "Cancel": {"cmd": self.cmdNo, "bind_none": True},
            "No": {"cmd": self.cmdNo, "bind_none": True},
            "Change height": {
                "cmd": self.cmdChgHeight,
                "bind_cmd": "/settings",
                "lastState": "/settings",
            },
            f"{self.main.gEmo('enter')} Enter height": {
                "cmd": self.cmdSetHeight,
                "bind_cmd": "/settings",
                "lastState": "Change height",
            },
            " Enter height": {
                "cmd": self.cmdSetHeight,
                "bind_cmd": "/settings",
                "lastState": "Change height",
            },
            "Change time": {
                "cmd": self.cmdChgTime,
                "bind_cmd": "/settings",
                "lastState": "/settings",
            },
            f"{self.main.gEmo('enter')} Enter time": {
                "cmd": self.cmdSetTime,
                "bind_cmd": "/settings",
                "lastState": "Change time",
            },
            " Enter time": {
                "cmd": self.cmdSetTime,
                "bind_cmd": "/settings",
                "lastState": "Change time",
            },
            "Start print": {
                "cmd": self.cmdStartPrint,
                "bind_cmd": "/print",
                "lastState": "/print_",
            },
            "Stop print": {
                "cmd": self.cmdHalt,
                "bind_cmd": "/abort",
                "lastState": "/abort",
            },
            "Don't print": {
                "cmd": self.cmdDontPrint,
                "bind_cmd": "/print",
                "lastState": "/print_",
            },
            "Do System Command": {
                "cmd": self.cmdSysRun,
                "bind_cmd": "/sys",
                "lastState": "/sys_",
            },
            "Connect": {
                "cmd": self.cmdConnect,
                "bind_cmd": "/connection",
                "lastState": "/connection",
            },
            "Disconnect": {
                "cmd": self.cmdDisconnect,
                "bind_cmd": "/connection",
                "lastState": "/connection",
            },
            "/print_": {"cmd": self.cmdRunPrint, "bind_cmd": "/print"},
            "/test": {"cmd": self.cmdTest},
            "/status": {"cmd": self.cmdStatus},
            "/abort": {"cmd": self.cmdAbort},
            "/togglepause": {"cmd": self.cmdTogglePause},
            "/connection": {"cmd": self.cmdConnection},
            "/settings": {"cmd": self.cmdSettings},
            "/shutup": {"cmd": self.cmdShutup},
            "/imsorrydontshutup": {"cmd": self.cmdNShutup},
            "/list": {"cmd": self.cmdList},
            "/print": {"cmd": self.cmdPrint},
            "/upload": {"cmd": self.cmdUpload},
            "/help": {"cmd": self.cmdHelp},
            "/sys": {"cmd": self.cmdSys},
            "/sys_": {"cmd": self.cmdSysReq, "bind_cmd": "/sys"},
            "/ctrl": {"cmd": self.cmdCtrl},
            "/ctrl_": {"cmd": self.cmdCtrlRun, "bind_cmd": "/ctrl"},
            "/user": {"cmd": self.cmdUser},
        }

    #######################
    def checkState(self, chat_id, cmd, parameter=""):
        if chat_id not in self.stateList:
            self.stateList[chat_id] = ["", ""]
        ret = True
        if "lastState" in self.commandDict[cmd]:
            if self.commandDict[cmd]["lastState"] != self.stateList[chat_id][0]:
                ret = False
        self.stateList[chat_id][0] = cmd
        if parameter is not None and parameter != "":
            self.stateList[chat_id][1] = parameter
        return ret

    #######################
    def cmdYes(self, chat_id, **kwargs):
        self.main.send_msg("Alright.", chatID=chat_id)

    #######################
    def cmdNo(self, chat_id, **kwargs):
        self.main.send_msg("Maybe next time.", chatID=chat_id)

    #######################
    def cmdTest(self, chat_id, **kwargs):
        self.main.send_msg(
            f"{self.main.gEmo('question')} Is this a test?\n\n",
            responses=["Yes", "No"],
            chatID=chat_id,
        )

    #######################
    def cmdStatus(self, chat_id, **kwargs):
        # if not self.main._printer.is_operational():
        # TODO: self.main._settings.get(['messages',str(kwargs['event']),'image'])
        # TODO: implement "Send webcam captured imaged even if the printer is not connected" #34
        # kwargs['with_image'] = True
        # self.main.send_msg(self.main.gEmo('warning') + " Not connected to a printer. Use \connection to connect."),chatID=chat_id,**kwargs)
        # elif self.main._printer.is_printing():
        self.main.on_event("StatusPrinting", {}, chatID=chat_id)
        # else:
        # self.main.on_event("StatusNotPrinting", {},chatID=chat_id)

    #######################
    def cmdSettings(self, chat_id, **kwargs):
        msg = (
            self.main.gEmo("settings")
            + " Current notification settings are:\n\n\n"
            + self.main.gEmo("height")
            + " height: mm\n\n"
            + self.main.gEmo("clock")
            + " time: min\n\n\n"
            + self.main.gEmo("question")
            + "Which value do you want to change?"
        )

        self.main.send_msg(
            msg,
            responses=[
                ["Change height", "Change height"],
                ["Change time", "Change time"],
                ["NoNoNo", "Cancel"],
            ],
            chatID=chat_id,
            noMarkup=True,
        )

    #######################
    def cmdChgHeight(self, chat_id, **kwargs):
        self.main.send_msg(
            f"{self.main.gEmo('enter')} Enter height",
            force_reply=True,
            chatID=chat_id,
            noMarkup=True,
        )

    #######################
    def cmdSetHeight(self, chat_id, parameter, **kwargs):
        self.main._settings["notification_height"] = float(parameter)
        self.main.send_msg(
            self.main.gEmo("height")
            + " Notification height is now "
            + str(self.main._settings["notification_height"])
            + "mm.",
            chatID=chat_id,
            msg_id=self.main.thread.get_update_msg_id(chat_id),
        )

    #######################
    def cmdChgTime(self, chat_id, **kwargs):
        self.main.send_msg(
            f"{self.main.gEmo('enter')} Enter time",
            force_reply=True,
            chatID=chat_id,
        )

    #######################
    def cmdSetTime(self, chat_id, parameter, **kwargs):
        self.main._settings["notification_time"] = int(parameter)
        self.main.send_msg(
            f"{self.main.gEmo('clock')} Notification time is now %(time)dmins.",
            time=self.main._settings["notification_time"],
            chatID=chat_id,
        )

    #######################
    def cmdAbort(self, chat_id, **kwargs):
        # if self.main._printer.is_printing():
        # self.main.send_msg(self.main.gEmo('question') + " Really abort the currently running print?", responses=["Stop print", "Cancel"],chatID=chat_id)
        # else:
        self.main.send_msg(
            self.main.gEmo("warning")
            + " Currently I'm not printing, so there is nothing to stop.",
            chatID=chat_id,
        )

    #######################
    def cmdTogglePause(self, chat_id, **kwargs):
        # msg = ""
        # if self.main._printer.is_printing():
        # msg = " Pausing the print."
        # self.main._printer.toggle_pause_print()
        # elif self.main._printer.is_paused():
        # msg = " Resuming the print."
        # self.main._printer.toggle_pause_print()
        # else:
        msg = "  Currently I'm not printing, so there is nothing to pause/resume."
        self.main.send_msg(self.main.gEmo("info") + msg, chatID=chat_id)

    #######################
    def cmdHalt(self, chat_id, **kwargs):
        self.main.send_msg(
            f"{self.main.gEmo('info')} Aborting the print.", chatID=chat_id
        )
        # self.main._printer.cancel_print()

    #######################
    def cmdDontPrint(self, chat_id, **kwargs):
        self.main._printer.unselect_file()
        self.main.send_msg("Maybe next time.", chatID=chat_id)

    #######################
    def cmdShutup(self, chat_id, **kwargs):
        if chat_id not in self.main.shut_up:
            self.main.shut_up[chat_id] = True
        self.main.send_msg(
            self.main.gEmo("noNotify")
            + " Okay, shutting up until the next print is finished."
            + self.main.gEmo("shutup")
            + " Use /imsorrydontshutup to let me talk again before that. ",
            chatID=chat_id,
        )

    #######################
    def cmdNShutup(self, chat_id, **kwargs):
        if chat_id in self.main.shut_up:
            del self.main.shut_up[chat_id]
        self.main.send_msg(
            f"{self.main.gEmo('notify')} Yay, I can talk again.", chatID=chat_id
        )

    #######################
    def cmdPrint(self, chat_id, **kwargs):
        self.main.send_msg(
            self.main.gEmo("info")
            + " Use /list to get a list of files and click the command beginning with /print after the correct file.",
            chatID=chat_id,
        )

    #######################
    def cmdRunPrint(self, chat_id, parameter, **kwargs):
        print("Looking for hash: %s", parameter)
        # destination, file = self.find_file_by_hash(parameter)
        # print("Destination: %s", destination)
        # print("File: %s", file)
        file = None
        if file is None or parameter is None or parameter == "":
            self.main.send_msg(
                self.main.gEmo("warning")
                + " I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /list again?",
                chatID=chat_id,
            )
            return
        # print("data: %s", self.main._printer.get_current_data())
        # print("state: %s", self.main._printer.get_current_job())
        # if destination==octoprint.filemanager.FileDestinations.SDCARD:
        # self.main._printer.select_file(file, True, printAfterSelect=False)
        # else:
        # file = self.main._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, file)
        # print("Using full path: %s", file)
        # self.main._printer.select_file(file, False, printAfterSelect=False)
        # data = self.main._printer.get_current_data()
        # if data['job']['file']['name'] is not None:
        # self.main.send_msg(self.main.gEmo('info') + " Okay. The file %(file)s is loaded.\n\n"+self.main.gEmo('question')+" Do you want me to start printing it now?", file=data['job']['file']['name']), responses=["Start print"), "Don't print")],chatID=chat_id)

    #######################
    def cmdStartPrint(self, chat_id, **kwargs):
        # data = self.main._printer.get_current_data()
        # if data['job']['file']['name'] is None:
        # self.main.send_msg(self.main.gEmo('warning') + " Uh oh... No file is selected for printing. Did you select one using /list?",chatID=chat_id)
        # return
        # if not self.main._printer.is_operational():
        # self.main.send_msg(self.main.gEmo('warning') + " Can't start printing: I'm not connected to a printer.",chatID=chat_id)
        # return
        # if self.main._printer.is_printing():
        # self.main.send_msg(self.main.gEmo('warning') + " A print job is already running. You can't print two thing at the same time. Maybe you want to use /abort?",chatID=chat_id)
        # return
        # self.main._printer.start_print()
        self.main.send_msg(
            f"{self.main.gEmo('rocket')} Started the print job.", chatID=chat_id
        )

    #######################
    def cmdList(self, chat_id, **kwargs):
        # files = self.get_flat_file_tree()
        self.main.send_msg(
            self.main.gEmo("save")
            + " File List:\n\n"
            + "\n"
            + "\n\n"
            + self.main.gEmo("info")
            + " You can click the command beginning with /print after a file to start printing this file.",
            chatID=chat_id,
        )

    #######################
    def cmdUpload(self, chat_id, **kwargs):
        self.main.send_msg(
            f"{self.main.gEmo('info')} To upload a gcode file, just send it to me.",
            chatID=chat_id,
        )

    #######################
    def cmdSys(self, chat_id, **kwargs):
        message = (
            self.main.gEmo("info")
            + " You have to pass a System Command. The following System Commands are known.\n(Click to execute)\n\n"
        )
        empty = True
        # for action in self.main._settings.global_get(['system','actions']):
        # empty = False
        # if action['action'] != "divider":
        # message += action['name'] + "\n/sys_" + self.hashMe(action['action'], 6) + "\n"
        # else:
        # message += "---------------------------\n"
        if empty:
            message += "No System Commands found..."
        self.main.send_msg(message, chatID=chat_id)

    #######################
    def cmdSysReq(self, chat_id, parameter, **kwargs):
        # if parameter is None or parameter is "":
        # kwargs['cmd'] = "/sys"
        # self.cmdSys(chat_id, **kwargs)
        # return
        # actions = self.main._settings.global_get(['system','actions'])
        # command = next((d for d in actions if 'action' in d and self.hashMe(d['action'], 6) == parameter) , False)
        # if command :
        # self.main.send_msg(self.main.gEmo('question') + " Really execute "+command['name']+"?",responses=["Do System Command", "Cancel"],chatID=chat_id)
        # return
        self.main.send_msg(
            f"{self.main.gEmo('warning')} Sorry, i don't know this System Command.",
            chatID=chat_id,
        )

    #######################
    def cmdSysRun(self, chat_id, **kwargs):
        # parameter = self.stateList[chat_id][1]
        # actions = self.main._settings.global_get(['system','actions'])
        # action = next((i for i in actions if self.hashMe(i['action'], 6) == parameter), False)
        ### The following is taken from OctoPrint/src/octoprint/server/api/__init__.py -> performSystemAction()
        # async = action["async"] if "async" in action else False
        # ignore = action["ignore"] if "ignore" in action else False
        # self._logger.info("Performing command: %s" % action["command"])
        # try:
        # we run this with shell=True since we have to trust whatever
        # our admin configured as command and since we want to allow
        # shell-alike handling here...
        # p = sarge.run(action["command"], stderr=sarge.Capture(), shell=True, async=async)
        # if not async:
        # if p.returncode != 0:
        # returncode = p.returncode
        # stderr_text = p.stderr.text
        # self._logger.warn("Command failed with return code %i: %s" % (returncode, stderr_text))
        # self.main.send_msg(self.main.gEmo('warning') + " Command failed with return code %i: %s" % (returncode, stderr_text),chatID=chat_id)
        # return
        # self.main.send_msg(self.main.gEmo('check') + " Command " + action["name"] + " executed." ,chatID=chat_id)
        # except Exception, e:
        # self._logger.warn("Command failed: %s" % e)
        # self.main.send_msg(self.main.gEmo('warning') + " Command failed with exception: %s!" % e,chatID = chat_id)
        return

    #######################
    def cmdCtrl(self, chat_id, **kwargs):
        message = (
            self.main.gEmo("info")
            + " You have to pass a Printer Control Command. The following Printer Controls are known.\n(Click to execute)\n\n"
        )
        empty = True
        # for action in self.get_controls_recursively():
        # empty=False
        # message += action['name'] + "\n/ctrl_" + action['hash'] + "\n"
        if empty:
            message += "No Printer Control Command found..."
        self.main.send_msg(message, chatID=chat_id)

    #######################
    def cmdCtrlRun(self, chat_id, parameter, **kwargs):
        # if parameter is None or parameter is "":
        # self.cmdCtrl(chat_id, **kwargs)
        # return
        # actions = self.get_controls_recursively()
        # command = next((d for d in actions if d['hash'] == parameter), False)
        # if command:
        # if type(command['command']) is type([]):
        # for key in command['command']:
        # self.main._printer.commands(key)
        # else:
        # self.main._printer.commands(command['command'])
        # self.main.send_msg(self.main.gEmo('check') + " Control Command " + command['name'] + " executed." ,chatID=chat_id)
        # else:
        self.main.send_msg(
            f"{self.main.gEmo('warning')} Control Command ctrl_{parameter} not found.",
            chatID=chat_id,
        )

    #######################
    def cmdUser(self, chat_id, **kwargs):
        msg = f"{self.main.gEmo('info')} *Your user settings:*\n\n"
        msg += f"*ID:* {str(chat_id)}\n"
        msg += f"*Name:* {str(self.main.chats[chat_id]['title'])}\n"
        if self.main.chats[chat_id]["private"]:
            msg += "*Type:* Private\n\n"
        else:
            msg += "*Type:* Group\n"
            if self.main.chats[chat_id]["accept_commands"]:
                msg += "*Accept-Commands:* All users\n\n"
            elif self.main.chats[chat_id]["allow_users"]:
                msg += "*Accept-Commands:* Allowed users\n\n"
            else:
                msg += "*Accept-comands:* None\n\n"

        msg += "*Allowed commands:*\n"
        if self.main.chats[chat_id]["accept_commands"]:
            myTmp = 0
            for key in self.main.chats[chat_id]["commands"]:
                if (
                    self.main.chats[chat_id]["commands"][key]
                    and "bind_cmd" not in self.commandDict[key]
                    and "bind_none" not in self.commandDict[key]
                ):
                    msg += f"{key}, "
                    myTmp += 1
            if myTmp < 1:
                msg += "You are NOT allowed to send any command."
            msg += "\n\n"
        elif self.main.chats[chat_id]["allow_users"]:
            msg += "Allowed users ONLY. See specific user settings for details.\n\n"
        else:
            msg += "You are NOT allowed to send any command.\n\n"

        msg += "*Get notification on:*\n"
        if self.main.chats[chat_id]["send_notifications"]:
            myTmp = 0
            for key in self.main.chats[chat_id]["notifications"]:
                if self.main.chats[chat_id]["notifications"][key]:
                    msg += f"{key}, "
                    myTmp += 1
            if myTmp < 1:
                msg += "You will receive NO notifications."
            msg += "\n\n"
        else:
            msg += "You will receive NO notifications.\n\n"

        self.main.send_msg(msg, chatID=chat_id, markup="Markdown")

    #######################
    def cmdConnection(self, chat_id, **kwargs):
        # if self.main._printer.is_operational():
        # if self.main._printer.is_printing() or self.main._printer.is_paused():
        # self.main.send_msg(self.main.gEmo('warning') + " You can't change connection state while printing.",chatID=chat_id)
        # else:
        # self.main.send_msg(self.main.gEmo('question') + " Printer is connected. Do you want to disconnect?",responses=["Disconnect", "Cancel"],chatID=chat_id)
        # else:
        self.main.send_msg(
            self.main.gEmo("question")
            + " Printer is not connected. Do you want to connect?",
            responses=["Connect", "Cancel"],
            chatID=chat_id,
        )

    #######################
    def cmdConnect(self, chat_id, **kwargs):
        # self.main._printer.connect()
        self.main.send_msg(
            f"{self.main.gEmo('info')} Connection started.", chatID=chat_id
        )

    #######################
    def cmdDisconnect(self, chat_id, **kwargs):
        # self.main._printer.disconnect()
        self.main.send_msg(
            f"{self.main.gEmo('info')} Printer disconnected.", chatID=chat_id
        )

    #######################
    def cmdHelp(self, chat_id, **kwargs):
        self.main.send_msg(
            self.main.gEmo("info") + " You can use following commands:\n\n"
            "/abort - Aborts the currently running print. A confirmation is required.\n"
            "/shutup - Disables automatic notifications till the next print ends.\n"
            "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
            "/status - Sends the current status including a current photo.\n"
            "/settings - Displays the current notification settings and allows you to change them.\n"
            "/list - Lists all the files available for printing and lets you start printing them.\n"
            "/print - Lets you start a print. A confirmation is required.\n"
            "/togglepause - Pause/Resume current Print.\n"
            "/connection - Connect/disconnect printer.\n"
            "/upload - You can just send me a gcode file to save it to my library.\n"
            "/sys - Execute Octoprint System Comamnds.\n"
            "/ctrl - Use self defined controls from Octoprint.\n"
            "/user - get user info.",
            chatID=chat_id,
        )

    #######################
    def get_flat_file_tree(self):
        # tree = self.main._file_manager.list_files(recursive=True)
        array = []
        # for key in tree:
        # array.append(key + ":")
        # array.extend(sorted(self.flatten_file_tree_recursively(tree[key])))
        return array

    def flatten_file_tree_recursively(self, tree, base=""):
        array = []
        # for key in tree:
        # if tree[key]['type']=="folder":
        # array.extend(self.flatten_file_tree_recursively(tree[key]['children'], base=base+key+"/"))
        # elif tree[key]['type']=="machinecode":
        # array.append(base+key + " - /print_" + tree[key]['hash'][0:8])
        # else:
        # array.append(base+key)
        return array

    def find_file_by_hash(self, hash):
        # tree = self.main._file_manager.list_files(recursive=True)
        # for key in tree:
        # result = self.find_file_by_hash_recursively(tree[key], hash)
        # if result is not None:
        # return key, result
        return None, None

    def find_file_by_hash_recursively(self, tree, hash, base=""):
        # for key in tree:
        # if tree[key]['type']=="folder":
        # result = self.find_file_by_hash_recursively(tree[key]['children'], hash, base=base+key+"/")
        # if result is not None:
        # return result
        # continue
        # if tree[key]['hash'].startswith(hash):
        # return base+key
        return None

    def get_controls_recursively(self, tree=None, base="", first=""):
        array = []
        # if tree == None:
        # tree = self.main._settings.global_get(['controls'])
        # for key in tree:
        # if type(key) is type({}):
        # if base == "":
        # first = " "+key['name']+" "
        # if 'children' in key:
        # array.extend(self.get_controls_recursively(key['children'], base + " " + key['name'],first))
        # elif ('commands' in key or 'command' in key) and not 'confirm' in key and not 'regex' in key and not 'input' in key and not 'script' in key:
        # rename 'commands' to 'command' so its easier to handle later on
        # newKey = {}
        # command = key['command'] if 'command' in key else key['commands']
        # newKey['name'] = base.replace(first,"") + " " + key['name']
        # newKey['hash'] = self.hashMe(base + " " + key['name'] + str(command), 6)
        # newKey['command'] = command
        # array.append(newKey)
        return array

    def hashMe(self, text, length):
        return hashlib.md5(text).hexdigest()[0:length]
