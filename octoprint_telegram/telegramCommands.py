import base64
import datetime
import hashlib
import operator
import socket

import octoprint.filemanager
import requests
import sarge
from octoprint.printer import UnknownScript

from .emoji.emoji import Emoji

get_emoji = Emoji.get_emoji


#################################################################################################################################
# This class handles received commands/messages (commands in the following). commandDict{} holds the commands and their behavior.
# Each command has its own handler. If you want to add/del commands, read the following:
# SEE DOCUMENTATION IN WIKI: https://github.com/jacopotediosi/OctoPrint-Telegram/wiki/Add%20commands%20and%20notifications
#################################################################################################################################
class TCMD:
    def __init__(self, main):
        self.main = main
        self._logger = main._logger.getChild("TCMD")
        self.SettingsTemp = []
        self.tuneTemp = [100, 100]
        self.tempTemp = []
        self.conSettingsTemp = []
        self.dirHashDict = {}
        self.tmpFileHash = ""
        self._spoolManagerPluginImplementation = None
        self.port = self.main.port
        self.commandDict = {
            "Yes": {"cmd": self.cmdYes, "bind_none": True},
            "No": {"cmd": self.cmdNo, "bind_none": True},
            "SwitchOn": {"cmd": self.cmdSwitchOn, "param": True},
            "SwitchOff": {"cmd": self.cmdSwitchOff, "param": True},
            "/test": {"cmd": self.cmdTest, "bind_none": True},
            "/status": {"cmd": self.cmdStatus},
            "/gif": {"cmd": self.cmdGif},
            "/supergif": {"cmd": self.cmdSuperGif},
            "/photo": {"cmd": self.cmdPhoto},
            "/settings": {"cmd": self.cmdSettings, "param": True},
            "/abort": {"cmd": self.cmdAbort, "param": True},
            "/togglepause": {"cmd": self.cmdTogglePause},
            "/home": {"cmd": self.cmdHome},
            "/shutup": {"cmd": self.cmdShutup},
            "/dontshutup": {"cmd": self.cmdNShutup},
            "/print": {"cmd": self.cmdPrint, "param": True},
            "/files": {"cmd": self.cmdFiles, "param": True},
            "/upload": {"cmd": self.cmdUpload},
            "/filament": {"cmd": self.cmdFilament, "param": True},
            "/sys": {"cmd": self.cmdSys, "param": True},
            "/ctrl": {"cmd": self.cmdCtrl, "param": True},
            "/off": {"cmd": self.cmdPrinterOff, "param": True},
            "/on": {"cmd": self.cmdPrinterOn, "param": True},
            "/con": {"cmd": self.cmdConnection, "param": True},
            "/user": {"cmd": self.cmdUser},
            "/tune": {"cmd": self.cmdTune, "param": True},
            "/help": {"cmd": self.cmdHelp, "bind_none": True},
            "/gcode": {"cmd": self.cmdGCode, "param": True},
        }

    ############################################################################################
    # COMMAND HANDLERS
    ############################################################################################
    def cmdYes(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            "Alright.",
            chatID=chat_id,
            msg_id=self.main.get_update_msg_id(chat_id),
            inline=False,
        )

    ############################################################################################
    def cmdNo(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            "Maybe next time.",
            chatID=chat_id,
            msg_id=self.main.get_update_msg_id(chat_id),
            inline=False,
        )

    ############################################################################################
    def cmdTest(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            f"{get_emoji('question')} Is this a test?\n\n",
            responses=[
                [
                    [f"{get_emoji('check')} Yes", "Yes"],
                    [f"{get_emoji('cancel')} No", "No"],
                ]
            ],
            chatID=chat_id,
        )

    ############################################################################################
    def cmdStatus(self, chat_id, from_id, cmd, parameter, user=""):
        if not self.main._printer.is_operational():
            with_image = self.main._settings.get_boolean(["image_not_connected"])
            self.main.send_msg(
                f"{get_emoji('warning')} Not connected to a printer. Use /con to connect.",
                chatID=chat_id,
                inline=False,
                with_image=with_image,
            )
        elif self.main._printer.is_printing():
            self.main.on_event("StatusPrinting", {}, chatID=chat_id)
        else:
            self.main.on_event("StatusNotPrinting", {}, chatID=chat_id)

    ############################################################################################
    def cmdGif(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._settings.get(["send_gif"]):
            self.main.send_msg(
                f"{get_emoji('video')} Here are your GIF(s)",
                chatID=chat_id,
                with_gif=True,
            )
        else:
            self.main.send_msg(
                f"{get_emoji('notallowed')} Sending GIFs is disabled in plugin settings",
                chatID=chat_id,
            )

    ############################################################################################
    def cmdSuperGif(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._settings.get(["send_gif"]):
            self.main.send_msg(
                f"{get_emoji('video')} Here are your GIF(s)",
                chatID=chat_id,
                with_gif=True,
                gif_duration=10,
            )
        else:
            self.main.send_msg(
                f"{get_emoji('notallowed')} Sending GIFs is disabled in plugin settings",
                chatID=chat_id,
            )

    ############################################################################################
    def cmdPhoto(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            f"{get_emoji('photo')} Here are your photo(s)",
            chatID=chat_id,
            with_image=True,
        )

    ############################################################################################
    def cmdSettings(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "h":
                if len(params) > 1:
                    if params[1].startswith("+"):
                        self.SettingsTemp[0] += float(100) / (10 ** len(params[1]))
                    elif params[1].startswith("-"):
                        self.SettingsTemp[0] -= float(100) / (10 ** len(params[1]))
                    else:
                        self.main._settings.set_float(["notification_height"], self.SettingsTemp[0], force=True)
                        self.main._settings.save()
                        self.cmdSettings(chat_id, from_id, cmd, "back", user)
                        return
                    if self.SettingsTemp[0] < 0:
                        self.SettingsTemp[0] = 0
                msg = f"{get_emoji('height')} Set new height.\nCurrent:  *{self.SettingsTemp[0]:.2f}mm*"
                keys = [
                    [
                        ["+10", "/settings_h_+"],
                        ["+1", "/settings_h_++"],
                        ["+.1", "/settings_h_+++"],
                        ["+.01", "/settings_h_++++"],
                    ],
                    [
                        ["-10", "/settings_h_-"],
                        ["-1", "/settings_h_--"],
                        ["-.1", "/settings_h_---"],
                        ["-.01", "/settings_h_----"],
                    ],
                    [
                        [f"{get_emoji('save')} Save", "/settings_h_s"],
                        [
                            f"{get_emoji('back')} Back",
                            "/settings_back",
                        ],
                    ],
                ]
                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="Markdown",
                )
            elif params[0] == "t":
                if len(params) > 1:
                    if params[1].startswith("+"):
                        self.SettingsTemp[1] += 100 / (10 ** len(params[1]))
                    elif params[1].startswith("-"):
                        self.SettingsTemp[1] -= 100 / (10 ** len(params[1]))
                    else:
                        self.main._settings.set_int(["notification_time"], self.SettingsTemp[1], force=True)
                        self.main._settings.save()
                        self.cmdSettings(chat_id, from_id, cmd, "back", user)
                        return
                    if self.SettingsTemp[1] < 0:
                        self.SettingsTemp[1] = 0
                msg = f"{get_emoji('alarmclock')} Set new time.\nCurrent: *{self.SettingsTemp[1]}min*"
                keys = [
                    [["+10", "/settings_t_+"], ["+1", "/settings_t_++"]],
                    [["-10", "/settings_t_-"], ["-1", "/settings_t_--"]],
                    [
                        [f"{get_emoji('save')} Save", "/settings_t_s"],
                        [
                            f"{get_emoji('back')} Back",
                            "/settings_back",
                        ],
                    ],
                ]
                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="Markdown",
                )
            elif params[0] == "g":
                if self.main._settings.get_boolean(["send_gif"]):
                    self.main._settings.set_int(["send_gif"], 0, force=True)
                else:
                    self.main._settings.set_int(["send_gif"], 1, force=True)
                self.main._settings.save()
                self.cmdSettings(chat_id, from_id, cmd, "back", user)
                return
        else:
            if self.main._settings.get_boolean(["send_gif"]):
                gif_txt = "Deactivate gif"
                gif_emo = get_emoji("check")
            else:
                gif_txt = "Activate gif"
                gif_emo = get_emoji("cancel")

            self.SettingsTemp = [
                self.main._settings.get_float(["notification_height"]),
                self.main._settings.get_float(["notification_time"]),
            ]
            msg = (
                f"{get_emoji('settings')} *Current notification settings are:*\n\n"
                f"{get_emoji('height')} Height: {self.main._settings.get_float(['notification_height']):.2f}mm\n\n"
                f"{get_emoji('alarmclock')} Time: {self.main._settings.get_int(['notification_time']):d}min\n\n"
                f"{get_emoji('video')} Gif is activate: {gif_emo}"
            )

            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(
                msg,
                responses=[
                    [
                        [
                            f"{get_emoji('height')} Set height",
                            "/settings_h",
                        ],
                        [
                            f"{get_emoji('alarmclock')} Set time",
                            "/settings_t",
                        ],
                        [
                            f"{get_emoji('video')} {gif_txt}",
                            "/settings_g",
                        ],
                    ],
                    [[f"{get_emoji('cancel')} Close", "No"]],
                ],
                chatID=chat_id,
                msg_id=msg_id,
                markup="Markdown",
            )

    ############################################################################################
    def cmdAbort(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter == "stop":
            self.main._printer.cancel_print(user=user)
            self.main.send_msg(
                f"{get_emoji('info')} Aborting the print.",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
        else:
            if self.main._printer.is_printing():
                self.main.send_msg(
                    f"{get_emoji('question')} Really abort the currently running print?",
                    responses=[
                        [
                            [
                                f"{get_emoji('check')} Stop print",
                                "/abort_stop",
                            ],
                            [f"{get_emoji('cancel')} Close", "No"],
                        ]
                    ],
                    chatID=chat_id,
                )
            else:
                self.main.send_msg(
                    f"{get_emoji('info')} Currently I'm not printing, so there is nothing to stop.",
                    chatID=chat_id,
                    inline=False,
                )

    ############################################################################################
    def cmdTogglePause(self, chat_id, from_id, cmd, parameter, user=""):
        msg = ""
        if self.main._printer.is_printing():
            msg = f"{get_emoji('pause')} Pausing the print."
            self.main._printer.toggle_pause_print(user=user)
        elif self.main._printer.is_paused():
            msg = f"{get_emoji('resume')} Resuming the print."
            self.main._printer.toggle_pause_print(user=user)
        else:
            msg = "  Currently I'm not printing, so there is nothing to pause/resume."
        self.main.send_msg(msg, chatID=chat_id, inline=False)

    ############################################################################################
    def cmdHome(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._printer.is_ready():
            msg = f"{get_emoji('home')} Homing."
            self.main._printer.home(["x", "y", "z"])
        else:
            msg = f"{get_emoji('warning')} I can't go home now."
        self.main.send_msg(msg, chatID=chat_id, inline=False)

    ############################################################################################
    def cmdShutup(self, chat_id, from_id, cmd, parameter, user=""):
        if chat_id not in self.main.shut_up:
            self.main.shut_up[chat_id] = 0
        self.main.shut_up[chat_id] += 1
        if self.main.shut_up[chat_id] >= 5:
            self._logger.warning(f"shut_up value is {self.main.shut_up[chat_id]}. Shutting down.")
            self.main.shutdown()
        self.main.send_msg(
            f"{get_emoji('nonotify')} Okay, shutting up until the next print is finished.\n"
            f"Use /dontshutup to let me talk again before that.",
            chatID=chat_id,
            inline=False,
        )

    ############################################################################################
    def cmdNShutup(self, chat_id, from_id, cmd, parameter, user=""):
        if chat_id in self.main.shut_up:
            self.main.shut_up[chat_id] = 0
        self.main.send_msg(
            f"{get_emoji('notify')} Yay, I can talk again.",
            chatID=chat_id,
            inline=False,
        )

    ############################################################################################
    def cmdPrint(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and len(parameter.split("|")) == 1:
            if parameter == "s":  # start print
                data = self.main._printer.get_current_data()
                if data["job"]["file"]["name"] is None:
                    self.main.send_msg(
                        f"{get_emoji('warning')} Uh oh... No file is selected for printing. Did you select one using /list?",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                elif not self.main._printer.is_operational():
                    self.main.send_msg(
                        f"{get_emoji('warning')} Can't start printing: I'm not connected to a printer.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                elif self.main._printer.is_printing():
                    self.main.send_msg(
                        f"{get_emoji('warning')} A print job is already running. You can't print two thing at the same time. Maybe you want to use /abort?",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                else:
                    self.main._printer.start_print(user=user)
                    self.main.send_msg(
                        f"{get_emoji('rocket')} Started the print job.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
            elif parameter == "x":  # do not print
                self.main._printer.unselect_file()
                self.main.send_msg(
                    "Maybe next time.",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            else:  # prepare print
                self._logger.debug(f"Looking for hash: {parameter}")
                destination, file, f = self.find_file_by_hash(parameter)
                if file is None:
                    msg = f"{get_emoji('warning')} I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /list again?"
                    self.main.send_msg(
                        msg,
                        chatID=chat_id,
                        noMarkup=True,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
                if destination == octoprint.filemanager.FileDestinations.SDCARD:
                    self.main._printer.select_file(file, True, printAfterSelect=False)
                else:
                    file = self.main._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, file)
                    self._logger.debug(f"Using full path: {file}")
                    self.main._printer.select_file(file, False, printAfterSelect=False)
                data = self.main._printer.get_current_data()
                if data["job"]["file"]["name"] is not None:
                    msg = (
                        f"{get_emoji('info')} Okay. The file {data['job']['file']['name']} is loaded.\n\n"
                        f"{get_emoji('question')} Do you want me to start printing it now?"
                    )
                    self.main.send_msg(
                        msg,
                        noMarkup=True,
                        msg_id=self.main.get_update_msg_id(chat_id),
                        responses=[
                            [
                                [
                                    f"{get_emoji('play')} Print",
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
                elif not self.main._printer.is_operational():
                    self.main.send_msg(
                        f"{get_emoji('warning')} Can't start printing: I'm not connected to a printer.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                else:
                    self.main.send_msg(
                        f"{get_emoji('warning')} Uh oh... Problems on loading the file for print.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
        else:
            self.cmdFiles(chat_id, from_id, cmd, parameter, user)

    ############################################################################################
    def cmdFiles(self, chat_id, from_id, cmd, parameter, user=""):
        try:
            if parameter:
                par = parameter.split("|")
                pathHash = par[0]
                page = int(par[1])
                fileHash = par[2] if len(par) > 2 else ""
                opt = par[3] if len(par) > 3 else ""
                if fileHash == "" and opt == "":
                    self.fileList(pathHash, page, cmd, chat_id)
                elif opt == "":
                    self.fileDetails(pathHash, page, cmd, fileHash, chat_id, from_id)
                else:
                    if opt.startswith("dir"):
                        self.fileList(fileHash, 0, cmd, chat_id)
                    else:
                        self.fileOption(pathHash, page, cmd, fileHash, opt, chat_id, from_id)
            else:
                storages = self.main._file_manager.list_files(recursive=False)
                if len(list(storages.keys())) < 2:
                    self.main.send_msg("Loading files...", chatID=chat_id)
                    self.generate_dir_hash_dict()
                    self.cmdFiles(
                        chat_id,
                        from_id,
                        cmd,
                        f"{self.hashMe(str(f'{list(storages.keys())[0]}/'), 8)}|0",
                        user,
                    )
                else:
                    self.generate_dir_hash_dict()
                    keys = []
                    keys.extend([([k, (f"{cmd}_{self.hashMe(k, 8)}/|0")] for k in storages)])
                    keys.append([[f"{get_emoji('cancel')} Close", "No"]])
                    msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
                    self.main.send_msg(
                        f"{get_emoji('save')} *Select Storage*",
                        chatID=chat_id,
                        markup="Markdown",
                        responses=keys,
                        msg_id=msg_id,
                    )
        except Exception:
            self._logger.exception("Command failed")
            self.main.send_msg(
                f"{get_emoji('warning')} Command failed, please check log files",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def cmdUpload(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            f"{get_emoji('info')} To upload a gcode file (also accept zip file), just send it to me.\nThe file will be stored in 'TelegramPlugin' folder.",
            chatID=chat_id,
        )

    ############################################################################################
    def cmdSys(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "sys":
                if params[1] != "do":
                    self.main.send_msg(
                        f"{get_emoji('question')} *{params[1]}*\nExecute system command?",
                        responses=[
                            [
                                [
                                    f"{get_emoji('check')} Execute",
                                    f"/sys_sys_do_{params[1]}",
                                ],
                                [
                                    f"{get_emoji('back')} Back",
                                    "/sys_back",
                                ],
                            ]
                        ],
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                        markup="Markdown",
                    )
                    return
                try:
                    if params[2] == "Restart OctoPrint":
                        myCmd = self.main._settings.global_get(["server", "commands", "serverRestartCommand"])
                    elif params[2] == "Reboot System":
                        myCmd = self.main._settings.global_get(["server", "commands", "systemRestartCommand"])
                    elif params[2] == "Shutdown System":
                        myCmd = self.main._settings.global_get(["server", "commands", "systemShutdownCommand"])

                    p = sarge.run(myCmd, stderr=sarge.Capture(), shell=True, async_=False)

                    if p.returncode != 0:
                        returncode = p.returncode
                        stderr_text = p.stderr.text
                        self._logger.warning(f"Command failed with return code {returncode}: {stderr_text}")
                        self.main.send_msg(
                            f"{get_emoji('warning')} Command failed with return code {returncode}: {stderr_text}",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
                        return
                    self.main.send_msg(
                        f"{get_emoji('check')} System Command executed.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                except Exception:
                    self._logger.exception("Command failed")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check log files",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
            elif params[0] == "do":
                parameter = params[1]
            else:
                parameter = params[0]
            actions = self.main._settings.global_get(["system", "actions"])
            command = next(
                (d for d in actions if "action" in d and self.hashMe(d["action"]) == parameter),
                False,
            )
            if command:
                if "confirm" in command and params[0] != "do":
                    self.main.send_msg(
                        f"{get_emoji('question')} {command['name']}\nExecute system command?",
                        responses=[
                            [
                                [
                                    f"{get_emoji('check')} Execute",
                                    f"/sys_do_{parameter}",
                                ],
                                [
                                    f"{get_emoji('back')} Back",
                                    "/sys_back",
                                ],
                            ]
                        ],
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
                else:
                    async_ = command["async"] if "async" in command else False
                    self._logger.info(f"Performing command: {command['command']}")
                    try:
                        # we run this with shell=True since we have to trust whatever
                        # our admin configured as command and since we want to allow
                        # shell-alike handling here...
                        p = sarge.run(
                            command["command"],
                            stderr=sarge.Capture(),
                            shell=True,
                            async_=async_,
                        )
                        if not async_:
                            if p.returncode != 0:
                                returncode = p.returncode
                                stderr_text = p.stderr.text
                                self._logger.warning(f"Command failed with return code {returncode}: {stderr_text}")
                                self.main.send_msg(
                                    f"{get_emoji('warning')} Command failed with return code {returncode}: {stderr_text}",
                                    chatID=chat_id,
                                    msg_id=self.main.get_update_msg_id(chat_id),
                                )
                                return
                        self.main.send_msg(
                            f"{get_emoji('check')} System Command {command['name']} executed.",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
                    except Exception:
                        self._logger.exception("Command failed")
                        self.main.send_msg(
                            f"{get_emoji('warning')} Command failed, please check log files",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
            else:
                self.main.send_msg(
                    f"{get_emoji('warning')} Sorry, i don't know this System Command.",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
                return
        else:
            keys = []
            tmpKeys = []
            i = 1
            for action in self.main._settings.global_get(["system", "actions"]):
                if action["action"] != "divider":
                    tmpKeys.append([f"{action['name']}", f"/sys_{self.hashMe(action['action'])}"])
                    if i % 2 == 0:
                        keys.append(tmpKeys)
                        tmpKeys = []
                    i += 1
            if len(tmpKeys) > 0:
                keys.append(tmpKeys)

            tmpKeys = []
            i = 1
            serverCommands = {
                "serverRestartCommand": [
                    "Restart OctoPrint",
                    "/sys_sys_Restart OctoPrint",
                ],
                "systemRestartCommand": ["Reboot System", "/sys_sys_Reboot System"],
                "systemShutdownCommand": [
                    "Shutdown System",
                    "/sys_sys_Shutdown System",
                ],
            }
            for index in serverCommands:
                commandText = self.main._settings.global_get(["server", "commands", index])
                if commandText is not None:
                    tmpKeys.append(serverCommands[index])
                    if i % 2 == 0:
                        keys.append(tmpKeys)
                        tmpKeys = []
                    i += 1
            if len(tmpKeys) > 0:
                keys.append(tmpKeys)

            if len(keys) > 0:
                message_text = " The following System Commands are known."
            else:
                message_text = " No known System Commands."
            try:
                self._logger.info(
                    f"IP: {self.main._settings.global_get(['server', 'host'])}:{self.main._settings.global_get(['server', 'port'])}"
                )

                server_ip = [
                    (
                        s.connect(
                            (
                                self.main._settings.global_get(["server", "onlineCheck", "host"]),
                                self.main._settings.global_get(["server", "onlineCheck", "port"]),
                            )
                        ),
                        s.getsockname()[0],
                        s.close(),
                    )
                    for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]
                ][0][1]
                if str(self.port) != "5000":
                    server_ip += f":{self.port}"
                message_text += f"\n\nIP: {server_ip}"
            except Exception:
                self._logger.exception("Exception retrieving IP address")

            message = f"{get_emoji('info')} {message_text}"

            keys.append([[f"{get_emoji('cancel')} Close", "No"]])
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)

    ############################################################################################
    def cmdCtrl(self, chat_id, from_id, cmd, parameter, user=""):
        if not self.main._printer.is_operational():
            self.main.send_msg(
                f"{get_emoji('warning')} Printer not connected. You can't send any command.",
                chatID=chat_id,
            )
            return
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "do":
                parameter = params[1]
            else:
                parameter = params[0]
            actions = self.get_controls_recursively()
            command = next((d for d in actions if d["hash"] == parameter), False)
            if command:
                if "confirm" in command and params[0] != "do":
                    self.main.send_msg(
                        f"{get_emoji('question')} {command['name']}\nExecute control command?",
                        responses=[
                            [
                                [
                                    f"{get_emoji('check')} Execute",
                                    f"/ctrl_do_{parameter}",
                                ],
                                [
                                    f"{get_emoji('back')} Back",
                                    "/ctrl_back",
                                ],
                            ]
                        ],
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
                else:
                    if "script" in command:
                        try:
                            self.main._printer.script(command["command"])
                        except UnknownScript:
                            self.main.send_msg(
                                f"{get_emoji('warning')} Unknown script: {command['command']}",
                                chatID=chat_id,
                                msg_id=self.main.get_update_msg_id(chat_id),
                            )
                    elif type(command["command"]) is type([]):
                        for key in command["command"]:
                            self.main._printer.commands(key)
                    else:
                        self.main._printer.commands(command["command"])
                    self.main.send_msg(
                        f"{get_emoji('check')} Control Command {command['name']} executed.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
            else:
                self.main.send_msg(
                    f"{get_emoji('warning')} Control Command not found.",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
        else:
            message = f"{get_emoji('info')} The following Printer Controls are known."
            empty = True
            keys = []
            tmpKeys = []
            i = 1
            try:
                for action in self.get_controls_recursively():
                    empty = False
                    try:
                        tmpKeys.append([f"{action['name']}", f"/ctrl_{action['hash']}"])
                        if i % 2 == 0:
                            keys.append(tmpKeys)
                            tmpKeys = []
                        i += 1
                    except Exception:
                        self._logger.exception("An Exception in get action")
                if len(tmpKeys) > 0:
                    keys.append(tmpKeys)
                keys.append([[f"{get_emoji('cancel')} Close", "No"]])
            except Exception:
                self._logger.exception("An Exception in get list action")
            if empty:
                message += f"\n\n{get_emoji('warning')} No Printer Control Command found..."
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)

    ############################################################################################
    def cmdPrinterOn(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._plugin_manager.get_plugin("psucontrol", True):
            try:  # Let's check if the printer has been turned on before.
                headers = {
                    "Content-Type": "application/json",
                    "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                }
                answer = requests.get(
                    f"http://localhost:{self.port}/api/plugin/psucontrol",
                    json={"command": "getPSUState"},
                    headers=headers,
                )
                if answer.status_code >= 300:  # It's not true that it's right. But so be it.
                    self._logger.debug(f"Call response (POST API octoprint): {answer}")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Something wrong, power on command failed.",
                        chatID=chat_id,
                    )
                else:
                    if answer.json()["isPSUOn"]:  # I know it's overcoding, but it's clearer.
                        self.main.send_msg(
                            f"{get_emoji('warning')} Printer has already been turned on.",
                            chatID=chat_id,
                        )
                        return
            except Exception:
                self._logger.exception("Failed to connect to call api")
                self.main.send_msg(
                    f"{get_emoji('warning')} Command failed, please check log files",
                    chatID=chat_id,
                )

            self.main.send_msg(
                f"{get_emoji('question')} Turn on the Printer?\n\n",
                responses=[
                    [
                        [f"{get_emoji('check')} Yes", "SwitchOn"],
                        [f"{get_emoji('cancel')} No", "No"],
                    ]
                ],
                chatID=chat_id,
            )
        elif (
            self.main._plugin_manager.get_plugin("tuyasmartplug", True)
            or self.main._plugin_manager.get_plugin("tasmota_mqtt", True)
            or self.main._plugin_manager.get_plugin("tplinksmartplug", True)
        ):
            if self.main._plugin_manager.get_plugin("tasmota_mqtt", True):
                plugpluginname = "tasmota_mqtt"
            elif self.main._plugin_manager.get_plugin("tplinksmartplug", True):
                plugpluginname = "tplinksmartplug"
            elif self.main._plugin_manager.get_plugin("tuyasmartplug", True):
                plugpluginname = "tuyasmartplug"
            if parameter and parameter != "back" and parameter != "No":
                try:  # Let's check if the printer has been turned on before.
                    params = parameter.split("_")
                    pluglabel = params[0]
                    if plugpluginname == "tasmota_mqtt":
                        relayN = params[1]
                        CurrentStatus = params[2]
                    else:
                        CurrentStatus = params[1]

                    if CurrentStatus == "on":
                        self.main.send_msg(
                            f"{get_emoji('warning')} Plug {pluglabel} has already been turned on.",
                            chatID=chat_id,
                        )
                        return
                except Exception:
                    self._logger.exception("Failed to connect to call api")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check log files",
                        chatID=chat_id,
                    )

                # self.main.send_msg(f"{get_emoji('question')} Turn on the Plug {pluglabel}?\n\n", responses=[[[get_emoji('check')+" Yes","SwitchOn",pluglabel], [get_emoji('cancel')+" No","No"]]],chatID=chat_id)
                self._logger.info("Attempting to turn on the printer with API")
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                    }
                    if plugpluginname == "tuyasmartplug":
                        data = f'{{ "command":"turnOn","label":"{pluglabel}" }}'
                    elif plugpluginname == "tasmota_mqtt":
                        data = f'{{ "command":"turnOn","topic":"{pluglabel}","relayN":"{relayN}" }}'
                    elif plugpluginname == "tplinksmartplug":
                        data = f'{{ "command":"turnOn","ip":"{pluglabel}" }}'
                    answer = requests.post(
                        f"http://localhost:{self.port}/api/plugin/{plugpluginname}",
                        headers=headers,
                        data=data,
                    )
                    if answer.status_code >= 300:
                        self._logger.debug(f"Call response (POST API octoprint): {answer}")
                        self.main.send_msg(
                            f"{get_emoji('warning')} Something wrong, Power on attempt failed.",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
                        return
                    self.main.send_msg(
                        f"{get_emoji('check')} Command executed.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                except Exception:
                    self._logger.exception("Failed to connect to call api")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check log files",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                return
            else:
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                    }
                    optionname = None
                    if plugpluginname == "tuyasmartplug":
                        data = '{ "command":"getListPlug","label":"all" }'
                        optionname = "arrSmartplugs"
                    elif plugpluginname == "tasmota_mqtt":
                        data = '{ "command":"getListPlug"}'
                        optionname = "arrRelays"
                    elif plugpluginname == "tplinksmartplug":
                        data = '{ "command":"getListPlug"}'
                        optionname = "arrSmartplugs"
                    self._logger.debug(f"http://localhost:{self.port}/api/plugin/{plugpluginname} | data={data}")
                    answer = requests.post(
                        f"http://localhost:{self.port}/api/plugin/{plugpluginname}",
                        headers=headers,
                        data=data,
                    )
                    force = True
                    if answer.status_code >= 300 or force:  # It's not true that it's right. But so be it.
                        self._logger.debug(f"Call response (POST API octoprint): {answer}")
                        # will try to get the list of plug from config
                        try:
                            curr = self.main._settings.global_get(["plugins", plugpluginname, optionname])
                            if curr is not None:
                                json_data = curr
                            else:
                                json_data = None
                        except Exception:
                            self._logger.exception("getting settings failed")
                            self.main.send_msg(
                                f"{get_emoji('warning')} Something wrong, power on command failed, please check log files.",
                                chatID=chat_id,
                            )
                            return
                    else:
                        self._logger.debug(f"Call response (POST API octoprint): {answer}")
                        json_data = answer.json()
                    keys = []
                    tmpKeys = []
                    message = "Which plug would you turn on "
                    firstplug = ""

                    if len(json_data) >= 1:
                        for label in json_data:
                            try:
                                if plugpluginname == "tuyasmartplug":
                                    tmpKeys.append(
                                        [
                                            f"{label['label']}",
                                            f"/on_{label['label']}_{label['currentState']}",
                                        ]
                                    )
                                    if firstplug == "":
                                        firstplug = f"{label['label']}"
                                elif plugpluginname == "tasmota_mqtt":
                                    tmpKeys.append(
                                        [
                                            f"{label['topic']}_{label['relayN']}",
                                            f"/on_{label['topic']}_{label['relayN']}_{label['currentstate']}",
                                        ]
                                    )
                                    if firstplug == "":
                                        firstplug = f"{label['topic']}_{label['relayN']}"
                                elif plugpluginname == "tplinksmartplug":
                                    tmpKeys.append(
                                        [
                                            f"{label['label']}",
                                            f"/on_{label['ip']}_{label['currentState']}",
                                        ]
                                    )
                                    if firstplug == "":
                                        firstplug = str(label["ip"])
                            except Exception:
                                self._logger.exception("Loop to add plug failed")

                        if len(json_data) == 1:
                            self.main.send_msg(
                                f"{get_emoji('question')} Turn on the Printer?\n\n",
                                responses=[
                                    [
                                        [
                                            f"{get_emoji('check')} Yes",
                                            f"SwitchOn_{firstplug}",
                                        ],
                                        [
                                            f"{get_emoji('cancel')} No",
                                            "No",
                                        ],
                                    ]
                                ],
                                chatID=chat_id,
                            )
                        else:
                            keys.append(tmpKeys)
                            keys.append(
                                [
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "No",
                                    ]
                                ]
                            )
                            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
                            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
                        return
                except Exception:
                    self._logger.exception("Command failed")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check log files",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
        else:
            self.main.send_msg(
                f"{get_emoji('warning')} PSU Control plugin not found. Command can not be executed.",
                chatID=chat_id,
            )

    ############################################################################################
    def cmdPrinterOff(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._plugin_manager.get_plugin("psucontrol", True):
            try:  # Let's check if the printer has been turned off before.
                headers = {
                    "Content-Type": "application/json",
                    "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                }
                answer = requests.get(
                    f"http://localhost:{self.port}/api/plugin/psucontrol",
                    json={"command": "getPSUState"},
                    headers=headers,
                )
                if answer.status_code >= 300:
                    self._logger.debug(f"Call response (POST API octoprint): {answer}")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Something wrong, shutdown failed.",
                        chatID=chat_id,
                    )
                else:
                    if not answer.json()["isPSUOn"]:
                        self.main.send_msg(
                            f"{get_emoji('warning')} Printer has already been turned off.",
                            chatID=chat_id,
                        )
                        return
            except Exception:
                self._logger.exception("Failed to connect to call api")
                self.main.send_msg(
                    f"{get_emoji('warning')} Command failed, please check log files",
                    chatID=chat_id,
                )

            self.main.send_msg(
                f"{get_emoji('question')} Turn off the Printer?\n\n",
                responses=[
                    [
                        [f"{get_emoji('check')} Yes", "SwitchOff"],
                        [f"{get_emoji('cancel')} No", "No"],
                    ]
                ],
                chatID=chat_id,
            )
        elif (
            self.main._plugin_manager.get_plugin("tuyasmartplug", True)
            or self.main._plugin_manager.get_plugin("tasmota_mqtt", True)
            or self.main._plugin_manager.get_plugin("tplinksmartplug", True)
        ):
            if self.main._plugin_manager.get_plugin("tasmota_mqtt", True):
                plugpluginname = "tasmota_mqtt"
            elif self.main._plugin_manager.get_plugin("tplinksmartplug", True):
                plugpluginname = "tplinksmartplug"
            elif self.main._plugin_manager.get_plugin("tuyasmartplug", True):
                plugpluginname = "tuyasmartplug"
            if parameter and parameter != "back" and parameter != "No":
                try:  # Let's check if the printer has been turned on before.
                    params = parameter.split("_")
                    pluglabel = params[0]
                    if plugpluginname == "tasmota_mqtt":
                        relayN = params[1]
                        CurrentStatus = params[2]
                    else:
                        CurrentStatus = params[1]

                    if CurrentStatus == "off":
                        self.main.send_msg(
                            f"{get_emoji('warning')} Plug {pluglabel} has already been turned off.",
                            chatID=chat_id,
                        )
                        return
                except Exception:
                    self._logger.exception("Failed to connect to call api")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check log files!",
                        chatID=chat_id,
                    )

                # self.main.send_msg(f"{get_emoji('question')} Turn on the Plug {pluglabel}?\n\n", responses=[[[f"{get_emoji('check')} Yes","SwitchOn",pluglabel], [f"{get_emoji('cancel')} No","No"]]],chatID=chat_id)
                self._logger.info("Attempting to turn off the printer with API")
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                    }
                    if plugpluginname == "tuyasmartplug":
                        data = f'{{ "command":"turnOff","label":"{pluglabel}" }}'
                    elif plugpluginname == "tasmota_mqtt":
                        data = f'{{ "command":"turnOff","topic":"{pluglabel}","relayN":"{relayN}" }}'
                    elif plugpluginname == "tplinksmartplug":
                        data = f'{{ "command":"turnOff","ip":"{pluglabel}" }}'
                    answer = requests.post(
                        f"http://localhost:{self.port}/api/plugin/{plugpluginname}",
                        headers=headers,
                        data=data,
                    )
                    if answer.status_code >= 300:
                        self._logger.debug(f"Call response (POST API octoprint): {answer}")
                        self.main.send_msg(
                            f"{get_emoji('warning')} Something wrong, Power off attempt failed.",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
                        return
                    self.main.send_msg(
                        f"{get_emoji('check')} Command executed.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                except Exception:
                    self._logger.exception("Failed to connect to call api")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check log files",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                return
            else:
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                    }
                    optionname = None
                    if plugpluginname == "tuyasmartplug":
                        data = '{ "command":"getListPlug","label":"all" }'
                        optionname = "arrSmartplugs"
                    elif plugpluginname == "tasmota_mqtt":
                        data = '{ "command":"getListPlug"}'
                        optionname = "arrRelays"
                    elif plugpluginname == "tplinksmartplug":
                        data = '{ "command":"getListPlug"}'
                        optionname = "arrSmartplugs"
                    self._logger.debug(f"http://localhost:{self.port}/api/plugin/{plugpluginname} | data={data}")
                    answer = requests.post(
                        f"http://localhost:{self.port}/api/plugin/{plugpluginname}",
                        headers=headers,
                        data=data,
                    )
                    force = True
                    if answer.status_code >= 300 or force:  # It's not true that it's right. But so be it.
                        self._logger.debug(f"Call response (POST API octoprint): {answer}")
                        # will try to get the list of plug from config
                        try:
                            curr = self.main._settings.global_get(["plugins", plugpluginname, optionname])
                            if curr is not None:
                                json_data = curr
                            else:
                                json_data = None
                        except Exception:
                            self._logger.exception("getting settings failed")
                            self.main.send_msg(
                                f"{get_emoji('warning')} Something wrong, power on command failed.",
                                chatID=chat_id,
                            )
                            return
                    else:
                        self._logger.debug(f"Call response (POST API octoprint): {answer}")
                        json_data = answer.json()

                    keys = []
                    tmpKeys = []
                    message = "Which plug would you turn off "
                    firstplug = ""
                    if len(json_data) >= 1:
                        for label in json_data:
                            try:
                                if plugpluginname == "tuyasmartplug":
                                    tmpKeys.append(
                                        [
                                            f"{label['label']}",
                                            f"/off_{label['label']}_{label['currentState']}",
                                        ]
                                    )
                                    if firstplug == "":
                                        firstplug = str(label["label"])
                                elif plugpluginname == "tasmota_mqtt":
                                    tmpKeys.append(
                                        [
                                            f"{label['topic']}_{label['relayN']}",
                                            f"/off_{label['topic']}_{label['relayN']}_{label['currentstate']}",
                                        ]
                                    )
                                    if firstplug == "":
                                        firstplug = f"{label['topic']}_{label['relayN']}"
                                elif plugpluginname == "tplinksmartplug":
                                    tmpKeys.append(
                                        [
                                            f"{label['label']}",
                                            f"/off_{label['ip']}_{label['currentState']}",
                                        ]
                                    )
                                    if firstplug == "":
                                        firstplug = f"{label['ip']}"
                            except Exception:
                                self._logger.exception("Loop to add plug failed")

                        if len(json_data) == 1:
                            self.main.send_msg(
                                f"{get_emoji('question')} Turn off the Printer?\n\n",
                                responses=[
                                    [
                                        [
                                            f"{get_emoji('check')} Yes",
                                            f"SwitchOff_{firstplug}",
                                        ],
                                        [
                                            f"{get_emoji('cancel')} No",
                                            "No",
                                        ],
                                    ]
                                ],
                                chatID=chat_id,
                            )
                        else:
                            keys.append(tmpKeys)
                            keys.append(
                                [
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "No",
                                    ]
                                ]
                            )
                            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
                            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
                        return
                except Exception:
                    self._logger.exception("Command failed")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Command failed, please check logs",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
        else:
            self.main.send_msg(
                f"{get_emoji('warning')} PSU Control plugin not found. Command can not be executed.",
                chatID=chat_id,
            )

    ############################################################################################
    def cmdSwitchOff(self, chat_id, from_id, cmd, parameter, user=""):
        self._logger.info("Shutting down printer with API")
        try:
            if self.main._plugin_manager.get_plugin("psucontrol", True):
                headers = {
                    "Content-Type": "application/json",
                    "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                }
                answer = requests.post(
                    f"http://localhost:{self.port}/api/plugin/psucontrol",
                    json={"command": "turnPSUOff"},
                    headers=headers,
                )

            elif (
                self.main._plugin_manager.get_plugin("tuyasmartplug", True)
                or self.main._plugin_manager.get_plugin("tasmota_mqtt", True)
                or self.main._plugin_manager.get_plugin("tplinksmartplug", True)
            ):
                if self.main._plugin_manager.get_plugin("tasmota_mqtt", True):
                    plugpluginname = "tasmota_mqtt"
                elif self.main._plugin_manager.get_plugin("tplinksmartplug", True):
                    plugpluginname = "tplinksmartplug"
                elif self.main._plugin_manager.get_plugin("tuyasmartplug", True):
                    plugpluginname = "tuyasmartplug"
                if parameter and parameter != "back" and parameter != "No":
                    try:  # Let's check if the printer has been turned on before.
                        params = parameter.split("_")
                        pluglabel = params[0]
                        if plugpluginname == "tuyasmartplug":
                            data = f'{{ "command":"turnOff","label":"{pluglabel}"  }}'
                        elif plugpluginname == "tasmota_mqtt":
                            relayN = params[1]
                            data = f'{{ "command":"turnOff","topic":"{pluglabel}","relayN":"{relayN}" }}'
                        elif plugpluginname == "tplinksmartplug":
                            data = f'{{ "command":"turnOff","ip":"{pluglabel}"  }}'
                        headers = {
                            "Content-Type": "application/json",
                            "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                        }
                        answer = requests.post(
                            f"http://localhost:{self.port}/api/plugin/{plugpluginname}",
                            headers=headers,
                            data=data,
                        )
                    except Exception:
                        self._logger.exception("Failed to connect to call api")
                        self.main.send_msg(
                            f"{get_emoji('warning')} Command failed, please check logs",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
                else:
                    self._logger.debug("should had parameters but not")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Something wrong, shutdown failed.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return
            if answer.status_code >= 300:
                self._logger.debug(f"Call response (POST API octoprint): {answer}")
                self.main.send_msg(
                    f"{get_emoji('warning')} Something wrong, shutdown failed.",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
                return
            self.main.send_msg(
                f"{get_emoji('check')} Shutdown Command executed.",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
        except Exception:
            self._logger.exception("Failed to connect to call api")
            self.main.send_msg(
                f"{get_emoji('warning')} Command failed, please check logs",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
        return

    ############################################################################################
    def cmdSwitchOn(self, chat_id, from_id, cmd, parameter, user=""):
        self._logger.info("Attempting to turn on the printer with API")
        try:
            if self.main._plugin_manager.get_plugin("psucontrol", True):
                headers = {
                    "Content-Type": "application/json",
                    "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                }
                answer = requests.post(
                    f"http://localhost:{self.port}/api/plugin/psucontrol",
                    json={"command": "turnPSUOn"},
                    headers=headers,
                )
            elif (
                self.main._plugin_manager.get_plugin("tuyasmartplug", True)
                or self.main._plugin_manager.get_plugin("tasmota_mqtt", True)
                or self.main._plugin_manager.get_plugin("tplinksmartplug", True)
            ):
                if self.main._plugin_manager.get_plugin("tasmota_mqtt", True):
                    plugpluginname = "tasmota_mqtt"
                elif self.main._plugin_manager.get_plugin("tplinksmartplug", True):
                    plugpluginname = "tplinksmartplug"
                elif self.main._plugin_manager.get_plugin("tuyasmartplug", True):
                    plugpluginname = "tuyasmartplug"
                if parameter and parameter != "back" and parameter != "No":
                    try:  # Let's check if the printer has been turned on before.
                        params = parameter.split("_")
                        pluglabel = params[0]
                        if plugpluginname == "tuyasmartplug":
                            data = f'{{ "command":"turnOn","label":"{pluglabel}"  }}'
                        elif plugpluginname == "tasmota_mqtt":
                            relayN = params[1]
                            data = f'{{ "command":"turnOn","topic":"{pluglabel}","relayN":"{relayN}" }}'
                        elif plugpluginname == "tplinksmartplug":
                            data = f'{{ "command":"turnOn","ip":"{pluglabel}"  }}'
                        self._logger.debug(
                            f"Call (POST API octoprint): url http://localhost:{self.port}/api/plugin/{plugpluginname} with data {data}"
                        )
                        headers = {
                            "Content-Type": "application/json",
                            "X-Api-Key": self.main._settings.global_get(["api", "key"]),
                        }
                        answer = requests.post(
                            f"http://localhost:{self.port}/api/plugin/{plugpluginname}",
                            headers=headers,
                            data=data,
                        )
                        self._logger.debug(
                            f"Call response (POST API octoprint): code {answer.status_code} with data {answer.text}"
                        )
                    except Exception:
                        self._logger.exception("Failed to connect to call api")
                        self.main.send_msg(
                            f"{get_emoji('warning')} Command failed, please check logs",
                            chatID=chat_id,
                            msg_id=self.main.get_update_msg_id(chat_id),
                        )
                else:
                    self._logger.debug("should had parameters but not")
                    self.main.send_msg(
                        f"{get_emoji('warning')} Something wrong, shutdown failed.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return

            if answer.status_code >= 300:
                self._logger.debug(f"Call response (POST API octoprint): {answer}")
                self.main.send_msg(
                    f"{get_emoji('warning')} Something wrong, Power on attempt failed.",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
                return
            self.main.send_msg(
                f"{get_emoji('check')} Command executed.",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
        except Exception:
            self._logger.exception("Failed to connect to call api")
            self.main.send_msg(
                f"{get_emoji('warning')} Command failed, please check logs",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
        return

    ############################################################################################
    def cmdUser(self, chat_id, from_id, cmd, parameter, user=""):
        msg = f"{get_emoji('info')} *Your user settings:*\n\n"
        msg += f"*ID:* {chat_id}\n"
        msg += f"*Name:* {self.main.chats[chat_id]['title']}\n"
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
                if self.main.chats[chat_id]["commands"][key]:
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

    ############################################################################################
    def cmdConnection(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("|")
            if params[0] == "s":
                self.ConSettings(chat_id, params[1:])
            elif params[0] == "c":
                self.ConConnect(chat_id, params[1:])
            elif params[0] == "d":
                self.ConDisconnect(chat_id)
        else:
            con = self.main._printer.get_current_connection()
            con2 = octoprint.printer.get_connection_options()
            msg = (
                f"{get_emoji('info')} Connection information\n\n"
                f"*Status*: {con[0]}\n\n"
                f"*Port*: {con[1]}\n"
                f"*Baud*: {'AUTO' if str(con[2]) == '0' else con[2]}\n"
                f"*Profile*: {con[3] if con[3] is None else con[3]['name']}\n"
                f"*AutoConnect*: {con2['autoconnect']}\n\n"
            )
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            if self.main._printer.is_operational():
                if self.main._printer.is_printing() or self.main._printer.is_paused():
                    self.main.send_msg(
                        f"{msg}{get_emoji('warning')} You can't disconnect while printing.",
                        responses=[
                            [
                                [
                                    f"{get_emoji('star')} Defaults",
                                    "/con_s",
                                ],
                                [
                                    f"{get_emoji('cancel')} Close",
                                    "No",
                                ],
                            ]
                        ],
                        chatID=chat_id,
                        msg_id=msg_id,
                        markup="Markdown",
                    )
                else:
                    self.main.send_msg(
                        msg,
                        responses=[
                            [
                                [
                                    f"{get_emoji('offline')} Disconnect",
                                    "/con_d",
                                ],
                                [
                                    f"{get_emoji('star')} Defaults",
                                    "/con_s",
                                ],
                                [
                                    f"{get_emoji('cancel')} Close",
                                    "No",
                                ],
                            ]
                        ],
                        chatID=chat_id,
                        msg_id=msg_id,
                        markup="Markdown",
                    )
            else:
                self.main.send_msg(
                    msg,
                    responses=[
                        [
                            [
                                f"{get_emoji('online')} Connect",
                                "/con_c",
                            ],
                            [
                                f"{get_emoji('star')} Defaults",
                                "/con_s",
                            ],
                            [f"{get_emoji('cancel')} Close", "No"],
                        ]
                    ],
                    chatID=chat_id,
                    msg_id=msg_id,
                    markup="Markdown",
                )

    ############################################################################################
    def cmdTune(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "feed":
                if len(params) > 1:
                    base = 1000
                    if params[1].endswith("*"):
                        base = 2500
                    if params[1].startswith("+"):
                        self.tuneTemp[0] += base / (10 ** len(params[1]))
                    elif params[1].startswith("-"):
                        self.tuneTemp[0] -= base / (10 ** len(params[1]))
                    else:
                        self.main._printer.feed_rate(int(self.tuneTemp[0]))
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return
                    if self.tuneTemp[0] < 50:
                        self.tuneTemp[0] = 50
                    elif self.tuneTemp[0] > 200:
                        self.tuneTemp[0] = 200
                msg = f"{get_emoji('feedrate')} Set feedrate.\nCurrent:  *{self.tuneTemp[0]}%*"
                keys = [
                    [
                        ["+25", "/tune_feed_+*"],
                        ["+10", "/tune_feed_++"],
                        ["+1", "/tune_feed_+++"],
                        ["-1", "/tune_feed_---"],
                        ["-10", "/tune_feed_--"],
                        ["-25", "/tune_feed_-*"],
                    ],
                    [
                        [f"{get_emoji('check')} Set", "/tune_feed_s"],
                        [
                            f"{get_emoji('back')} Back",
                            "/tune_back",
                        ],
                    ],
                ]
                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="Markdown",
                )
            elif params[0] == "flow":
                if len(params) > 1:
                    base = 1000
                    if params[1].endswith("*"):
                        base = 2500
                    if params[1].startswith("+"):
                        self.tuneTemp[1] += base / (10 ** len(params[1]))
                    elif params[1].startswith("-"):
                        self.tuneTemp[1] -= base / (10 ** len(params[1]))
                    else:
                        self.main._printer.flow_rate(int(self.tuneTemp[1]))
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return
                    if self.tuneTemp[1] < 50 or self.tuneTemp[1] > 200:
                        self.tuneTemp[1] = 200
                msg = f"{get_emoji('flowrate')} Set flowrate.\nCurrent: *{self.tuneTemp[1]}%*"
                keys = [
                    [
                        ["+25", "/tune_flow_+*"],
                        ["+10", "/tune_flow_++"],
                        ["+1", "/tune_flow_+++"],
                        ["-1", "/tune_flow_---"],
                        ["-10", "/tune_flow_--"],
                        ["-25", "/tune_flow_-*"],
                    ],
                    [
                        [f"{get_emoji('check')} Set", "/tune_flow_s"],
                        [
                            f"{get_emoji('back')} Back",
                            "/tune_back",
                        ],
                    ],
                ]
                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="Markdown",
                )
            elif params[0] == "e":
                temps = self.main._printer.get_current_temperatures()
                toolNo = int(params[1])
                if len(params) > 2:
                    base = 1000
                    if params[2].endswith("*"):
                        base = 5000
                    if params[2].startswith("+"):
                        self.tempTemp[toolNo] += base / (10 ** len(params[2]))
                    elif params[2].startswith("-"):
                        self.tempTemp[toolNo] -= base / (10 ** len(params[2]))
                    elif params[2].startswith("s"):
                        self.main._printer.set_temperature(f"tool{toolNo}", self.tempTemp[toolNo])
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return
                    else:
                        self.main._printer.set_temperature(f"tool{toolNo}", 0)
                        self.tempTemp[toolNo] = 0
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return
                    if self.tempTemp[toolNo] < 0:
                        self.tempTemp[toolNo] = 0
                msg = (
                    f"{get_emoji('tool')} Set temperature for tool {params[1]}.\n"
                    f"Current: {temps[f'tool{params[1]}']['actual']:.02f}/*{self.tempTemp[toolNo]}\u00b0C*"
                )
                keys = [
                    [
                        ["+100", f"/tune_e_{params[1]}_+"],
                        ["+50", f"/tune_e_{params[1]}_+*"],
                        ["+10", f"/tune_e_{params[1]}_++"],
                        ["+5", f"/tune_e_{params[1]}_++*"],
                        ["+1", f"/tune_e_{params[1]}_+++"],
                    ],
                    [
                        ["-100", f"/tune_e_{params[1]}_-"],
                        ["-50", f"/tune_e_{params[1]}_-*"],
                        ["-10", f"/tune_e_{params[1]}_--"],
                        ["-5", f"/tune_e_{params[1]}_--*"],
                        ["-1", f"/tune_e_{params[1]}_---"],
                    ],
                    [
                        [
                            f"{get_emoji('check')} Set",
                            f"/tune_e_{params[1]}_s",
                        ],
                        [
                            f"{get_emoji('cooldown')} Off",
                            f"/tune_e_{params[1]}_off",
                        ],
                        [
                            f"{get_emoji('back')} Back",
                            "/tune_back",
                        ],
                    ],
                ]
                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="Markdown",
                )
            elif params[0] == "b":
                temps = self.main._printer.get_current_temperatures()
                toolNo = len(self.tempTemp) - 1
                if len(params) > 1:
                    base = 1000
                    if params[1].endswith("*"):
                        base = 5000
                    if params[1].startswith("+"):
                        self.tempTemp[toolNo] += base / (10 ** len(params[1]))
                    elif params[1].startswith("-"):
                        self.tempTemp[toolNo] -= base / (10 ** len(params[1]))
                    elif params[1].startswith("s"):
                        self.main._printer.set_temperature("bed", self.tempTemp[toolNo])
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return
                    else:
                        self.main._printer.set_temperature("bed", 0)
                        self.tempTemp[toolNo] = 0
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return
                    if self.tempTemp[toolNo] < 0:
                        self.tempTemp[toolNo] = 0
                self._logger.debug(f"BED TEMPS: {temps}")
                self._logger.debug(f"BED self.TEMPS: {self.tempTemp}")
                msg = (
                    f"{get_emoji('hotbed')} Set temperature for bed.\n"
                    f"Current: {temps['bed']['actual']:.02f}/*{self.tempTemp[toolNo]}\u00b0C*"
                )
                keys = [
                    [
                        ["+100", "/tune_b_+"],
                        ["+50", "/tune_b_+*"],
                        ["+10", "/tune_b_++"],
                        ["+5", "/tune_b_++*"],
                        ["+1", "/tune_b_+++"],
                    ],
                    [
                        ["-100", "/tune_b_-"],
                        ["-50", "/tune_b_-*"],
                        ["-10", "/tune_b_--"],
                        ["-5", "/tune_b_--*"],
                        ["-1", "/tune_b_---"],
                    ],
                    [
                        [f"{get_emoji('check')} Set", "/tune_b_s"],
                        [f"{get_emoji('cooldown')} Off", "/tune_b_off"],
                        [
                            f"{get_emoji('back')} Back",
                            "/tune_back",
                        ],
                    ],
                ]
                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="Markdown",
                )
        else:
            msg = f"{get_emoji('settings')} *Tune print settings*"
            profile = self.main._printer_profile_manager.get_current()
            temps = self.main._printer.get_current_temperatures()
            self.tempTemp = []
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            keys = [
                [
                    [
                        f"{get_emoji('feedrate')} Feedrate",
                        "/tune_feed",
                    ],
                    [
                        f"{get_emoji('flowrate')} Flowrate",
                        "/tune_flow",
                    ],
                ]
            ]
            if self.main._printer.is_operational():
                tmpKeys = []
                for i in range(0, profile["extruder"]["count"]):
                    tmpKeys.append(
                        [
                            f"{get_emoji('tool')} Tool {i}",
                            f"/tune_e_{i}",
                        ]
                    )
                    self.tempTemp.append(int(temps[f"tool{i}"]["target"]))
                if profile["heatedBed"]:
                    tmpKeys.append([f"{get_emoji('hotbed')} Bed", "/tune_b"])
                    self.tempTemp.append(int(temps["bed"]["target"]))
                keys.append(tmpKeys)
            keys.append([[f"{get_emoji('cancel')} Close", "No"]])
            self.main.send_msg(msg, responses=keys, chatID=chat_id, msg_id=msg_id, markup="Markdown")

    ############################################################################################
    def cmdFilament(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._plugin_manager.get_plugin("filamentmanager", True):
            if parameter and parameter != "back":
                self._logger.info(f"Parameter received for filament: {parameter}")
                params = parameter.split("_")
                apikey = self.main._settings.global_get(["api", "key"])
                errorText = ""
                if params[0] == "spools":
                    try:
                        resp = requests.get(
                            f"http://localhost:{self.port}/plugin/filamentmanager/spools?apikey={apikey}"
                        )
                        resp2 = requests.get(
                            f"http://localhost:{self.port}/plugin/filamentmanager/selections?apikey={apikey}"
                        )
                        if resp.status_code != 200:
                            errorText = resp.text
                        resp = resp.json()
                        resp2 = resp2.json()
                        self._logger.info(f"Spools: {resp['spools']}")
                        message = f"{get_emoji('info')} Available filament spools are:\n"
                        for spool in resp["spools"]:
                            weight = spool["weight"]
                            used = spool["used"]
                            percent = int(100 - (used / weight * 100))
                            message += f"{spool['profile']['vendor']} {spool['name']} {spool['profile']['material']} [{percent}%]\n"
                        for selection in resp2["selections"]:
                            if selection["tool"] == 0:
                                message += (
                                    f"\n\nCurrently selected: "
                                    f"{selection['spool']['profile']['vendor']} "
                                    f"{selection['spool']['name']} "
                                    f"{selection['spool']['profile']['material']}"
                                )
                        msg_id = self.main.get_update_msg_id(chat_id)
                        self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                    except ValueError:
                        message = f"{get_emoji('attention')} Error getting spools. Are you sure, you have installed the Filament Manager Plugin?"
                        if errorText != "":
                            message += f"\nError text: {errorText}"
                        msg_id = self.main.get_update_msg_id(chat_id)
                        self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                if params[0] == "changeSpool":
                    self._logger.info(f"Command to change spool: {params}")
                    if len(params) > 1:
                        self._logger.info(f"Changing to spool: {params[1]}")
                        try:
                            payload = {"selection": {"spool": {"id": params[1]}, "tool": 0}}
                            self._logger.info(f"Payload: {payload}")
                            resp = requests.patch(
                                f"http://localhost:{self.port}/plugin/filamentmanager/selections/0?apikey={apikey}",
                                json=payload,
                                headers={"Content-Type": "application/json"},
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            self._logger.info(f"Response: {resp}")
                            resp = resp.json()
                            message = (
                                f"{get_emoji('check')} Selected spool is now: "
                                f"{resp['selection']['spool']['profile']['vendor']} "
                                f"{resp['selection']['spool']['name']} "
                                f"{resp['selection']['spool']['profile']['material']}"
                            )
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                        except ValueError:
                            message = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                message += f"\nError text: {errorText}"
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                    else:
                        self._logger.info("Asking for spool")
                        try:
                            resp = requests.get(
                                f"http://localhost:{self.port}/plugin/filamentmanager/spools?apikey={apikey}"
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            resp = resp.json()
                            message = f"{get_emoji('question')} which filament spool do you want to select?"
                            keys = []
                            tmpKeys = []
                            i = 1
                            for spool in resp["spools"]:
                                self._logger.info(f"Appending spool: {spool}")
                                tmpKeys.append(
                                    [
                                        f"{spool['profile']['vendor']} {spool['name']} {spool['profile']['material']}",
                                        f"/filament_changeSpool_{spool['id']}",
                                    ]
                                )
                                if i % 2 == 0:
                                    keys.append(tmpKeys)
                                    tmpKeys = []
                                i += 1
                            if len(tmpKeys) > 0:
                                keys.append(tmpKeys)
                            keys.append(
                                [
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "No",
                                    ]
                                ]
                            )
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self._logger.info("Sending message")
                            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
                        except ValueError:
                            message = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                message += f"\nError text: {errorText}"
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
            else:
                message = f"{get_emoji('info')} The following Filament Manager commands are known."
                keys = []
                keys.append([["Show spools", "/filament_spools"]])
                keys.append([["Change spool", "/filament_changeSpool"]])
                keys.append([[f"{get_emoji('cancel')} Close", "No"]])
                msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
                self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
        elif self.main._plugin_manager.get_plugin("SpoolManager", True):
            if parameter and parameter != "back":
                self._logger.info(f"Parameter received for filament: {parameter}")
                params = parameter.split("_")
                apikey = self.main._settings.global_get(["api", "key"])
                errorText = ""
                if params[0] == "spools":
                    try:
                        if self._spoolManagerPluginImplementation is None:
                            self._spoolManagerPluginImplementation = self.main._plugin_manager.get_plugin(
                                "SpoolManager", True
                            )
                        message = (
                            f"SpoolManager: {self._spoolManagerPluginImplementation.SpoolManagerAPI.load_allSpools()}"
                        )
                        # selectedSpool = self._spoolManagerPluginImplementation.filamentManager.loadSelectedSpool()
                        # allSpool = self._spoolManagerPluginImplementation.filamentManager.load_allSpools
                        # message = f"selectedSpool={selectedSpool}\nallSpool={allSpool}"

                        # resp = requests.get(f"http://localhost:{self.port}/plugin/spoolmanager/loadSpoolsByQuery?={query}")
                        # resp2 = requests.get(f"http://localhost:{self.port}/plugin/filamentmanager/selections?apikey={apikey}")
                        # if (resp.status_code != 200):
                        # 	errorText = resp.text
                        # resp = resp.json()
                        # resp2 = resp2.json()
                        # self._logger.info(f"Spools: {resp['spools']}")
                        # message = get_emoji('info') + " Available filament spools are:\n"
                        # for spool in resp["spools"]:
                        # 	weight = spool["weight"]
                        # 	used = spool["used"]
                        # 	percent = int(100 - (used / weight * 100))
                        # 	message += str(spool["profile"]["vendor"]) + " " + str(spool["name"]) + " " + str(spool["profile"]["material"]) + " [" + str(percent) + "%]\n"
                        # for selection in resp2["selections"]:
                        # 	if selection["tool"] == 0:
                        # 		message += "\n\nCurrently selected: " + str(selection["spool"]["profile"]["vendor"]) + " " + str(selection["spool"]["name"]) + " " + str(selection["spool"]["profile"]["material"])
                        msg_id = self.main.get_update_msg_id(chat_id)
                        self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                    except ValueError:
                        message = f"{get_emoji('attention')} Error getting spools. Are you sure you have installed the Spool Manager Plugin?"
                        if errorText != "":
                            message += f"\nError text: {errorText}"
                        msg_id = self.main.get_update_msg_id(chat_id)
                        self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                if params[0] == "changeSpool":
                    self._logger.info(f"Command to change spool: {params}")
                    if len(params) > 1:
                        self._logger.info(f"Changing to spool: {params[1]}")
                        try:
                            payload = {"selection": {"spool": {"id": params[1]}, "tool": 0}}
                            self._logger.info(f"Payload: {payload}")
                            resp = requests.patch(
                                f"http://localhost:{self.port}/plugin/filamentmanager/selections/0?apikey={apikey}",
                                json=payload,
                                headers={"Content-Type": "application/json"},
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            self._logger.info(f"Response: {resp}")
                            resp = resp.json()
                            message = (
                                f"{get_emoji('check')} Selected spool is now: "
                                f"{resp['selection']['spool']['profile']['vendor']} "
                                f"{resp['selection']['spool']['name']} "
                                f"{resp['selection']['spool']['profile']['material']}"
                            )
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                        except ValueError:
                            message = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                message += f"\nError text: {errorText}"
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
                    else:
                        self._logger.info("Asking for spool")
                        try:
                            resp = requests.get(
                                f"http://localhost:{self.port}/plugin/filamentmanager/spools?apikey={apikey}"
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            resp = resp.json()
                            message = f"{get_emoji('question')} which filament spool do you want to select?"
                            keys = []
                            tmpKeys = []
                            i = 1
                            for spool in resp["spools"]:
                                self._logger.info(f"Appending spool: {spool}")
                                tmpKeys.append(
                                    [
                                        f"{spool['profile']['vendor']} {spool['name']} {spool['profile']['material']}",
                                        f"/filament_changeSpool_{spool['id']}",
                                    ]
                                )
                                if i % 2 == 0:
                                    keys.append(tmpKeys)
                                    tmpKeys = []
                                i += 1
                            if len(tmpKeys) > 0:
                                keys.append(tmpKeys)
                            keys.append(
                                [
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "No",
                                    ]
                                ]
                            )
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self._logger.info("Sending message")
                            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
                        except ValueError:
                            message = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                message += f"\nError text: {errorText}"
                            msg_id = self.main.get_update_msg_id(chat_id)
                            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id, inline=False)
            else:
                message = f"{get_emoji('info')} The following Filament Manager commands are known."
                keys = []
                keys.append([["Show spools", "/filament_spools"]])
                keys.append([["Change spool", "/filament_changeSpool"]])
                keys.append([[f"{get_emoji('cancel')} Close", "No"]])
                msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
                self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
        else:
            message = f"{get_emoji('warning')} No filament manager plugin installed."
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id)

    ###########################################################################################
    def cmdGCode(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            self.main._printer.commands(params[0])
        else:
            message = f"{get_emoji('info')} call gCode commande with /gcode_XXX where XXX is the gcode command"
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id)

    ############################################################################################
    def cmdHelp(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._plugin_manager.get_plugin("psucontrol", True):
            switch_command = "/off - Switch off the Printer.\n/on - Switch on the Printer.\n"
        else:
            switch_command = ""
        self.main.send_msg(
            (
                f"{get_emoji('info')} *The following commands are known:*\n\n"
                "/abort - Aborts the currently running print. A confirmation is required.\n"
                "/shutup - Disables automatic notifications till the next print ends.\n"
                "/dontshutup - The opposite of /shutup - Makes the bot talk again.\n"
                "/status - Sends the current status including a current photo.\n"
                f"/gif - Sends a gif from the current video. {get_emoji('warning')}\n"
                "/supergif - Sends a bigger gif from the current video.\n"
                "/photo - Sends a photo from webcams.\n"
                "/settings - Displays the current notification settings and allows you to change them.\n"
                "/files - Lists all the files available for printing.\n"
                "/filament - Shows you your filament spools or lets you change it. Requires the Filament Manager Plugin.\n"
                "/print - Lets you start a print. A confirmation is required.\n"
                "/togglepause - Pause/Resume current Print.\n"
                "/home - Home the printer print head.\n"
                "/con - Connect/disconnect printer.\n"
                "/upload - You can just send me a gcode file or a zip file to save it to my library.\n"
                "/sys - Execute Octoprint System Commands.\n"
                "/ctrl - Use self defined controls from Octoprint.\n"
                "/tune - Set feed- and flowrate. Control temperatures.\n"
                "/user - Get user info.\n"
            )
            + switch_command
            + "/help - Show this help message.",
            chatID=chat_id,
            markup="Markdown",
        )

    ############################################################################################
    # FILE HELPERS
    ############################################################################################
    def fileList(self, pathHash, page, cmd, chat_id, wait=0):
        try:
            fullPath = self.dirHashDict[pathHash]
            dest = fullPath.split("/")[0]
            pathWoDest = "/".join(fullPath.split("/")[1:]) if len(fullPath.split("/")) > 1 else fullPath
            path = "/".join(fullPath.split("/")[1:])
            self._logger.debug(f"fileList path : {path}")
            fileList = self.main._file_manager.list_files(path=path, recursive=False)
            files = fileList[dest]
            arrayD = []
            self._logger.debug("fileList before loop folder ")
            M = {k: v for k, v in files.items() if v["type"] == "folder"}
            for key in M:
                arrayD.append(
                    [
                        f"{get_emoji('folder')} {key}",
                        f"{cmd}_{pathHash}|0|{self.hashMe(fullPath + key + '/', 8)}|dir",
                    ]
                )
            array = []
            self._logger.debug("fileList before loop files items")
            L = {k: v for k, v in files.items() if v["type"] == "machinecode"}
            for key, val in sorted(iter(L.items()), key=lambda x: x[1]["date"], reverse=True):
                try:
                    self._logger.debug("should get info on item ")
                    try:
                        if val.get("history"):
                            HistList = val["history"]
                            HistList.sort(key=lambda x: x["timestamp"], reverse=True)
                            try:
                                if HistList[0]["success"]:
                                    vfilename = f"{get_emoji('hooray')} {'.'.join(key.split('.')[:-1])}"
                                else:
                                    vfilename = f"{get_emoji('warning')} {'.'.join(key.split('.')[:-1])}"
                            except Exception:
                                vfilename = f"{get_emoji('file')} {'.'.join(key.split('.')[:-1])}"
                        else:
                            vfilename = f"{get_emoji('new')} {'.'.join(key.split('.')[:-1])}"
                    except Exception:
                        self._logger.exception("Caught an exception in fileList loop file items")
                        vfilename = f"{get_emoji('file')} {'.'.join(key.split('.')[:-1])}"

                    self._logger.debug(f"vfilename : {vfilename}")
                    vhash = self.hashMe(pathWoDest + key)
                    self._logger.debug(f"vhash : {vhash}")
                    if vhash != "":
                        vcmd = f"{cmd}_{pathHash}|{page}|{vhash}"
                        self._logger.debug(f"cmd : {cmd}")
                        array.append([vfilename, vcmd])
                except Exception:
                    self._logger.exception("Caught an exception in fileList loop file items")
                    self._logger.error(f"files[key]{files[key]}")
            arrayD = sorted(arrayD)
            if not self.main._settings.get_boolean(["fileOrder"]):
                arrayD.extend(sorted(array))
            else:
                arrayD.extend(array)
            files = arrayD
            pageDown = page - 1 if page > 0 else 0
            pageUp = page + 1 if len(files) - (page + 1) * 10 > 0 else page
            keys = []
            tmpKeys = []
            i = 1
            self._logger.debug("fileList before check nbpages ")
            for k in files[page * 10 : page * 10 + 10]:
                tmpKeys.append(k)
                if not i % 2:
                    keys.append(tmpKeys)
                    tmpKeys = []
                i += 1
            if len(tmpKeys):
                keys.append(tmpKeys)
            tmpKeys = []
            backBut = (
                [
                    [
                        f"{get_emoji('settings')} Settings",
                        f"{cmd}_{pathHash}|{page}|0|s",
                    ],
                    [f"{get_emoji('cancel')} Close", "No"],
                ]
                if len(fullPath.split("/")) < 3
                else [
                    [
                        f"{get_emoji('back')} Back",
                        f"{cmd}_{self.hashMe('/'.join(fullPath.split('/')[:-2]) + '/', 8)}|0",
                    ],
                    [
                        f"{get_emoji('settings')} Settings",
                        f"{cmd}_{pathHash}|{page}|0|s",
                    ],
                    [
                        f"{get_emoji('cancel')} Close",
                        "No",
                    ],
                ]
            )
            if pageDown != pageUp:
                if pageDown != page:
                    tmpKeys.append(
                        [
                            get_emoji("left"),
                            f"{cmd}_{pathHash}|{pageDown}",
                        ]
                    )
                if pageUp != page:
                    tmpKeys.append(
                        [
                            get_emoji("right"),
                            f"{cmd}_{pathHash}|{pageUp}",
                        ]
                    )
                tmpKeys.extend(backBut)

            else:
                tmpKeys.extend(backBut)
            keys.append(tmpKeys)
            pageStr = f"{page + 1}/{len(files) / 10 + (1 if len(files) % 10 > 0 else 0)}"
            self._logger.debug("fileList before send msg ")
            self.main.send_msg(
                f"{get_emoji('save')} Files in */{pathWoDest[:-1]}*    \\[{pageStr}]",
                chatID=chat_id,
                markup="Markdown",
                responses=keys,
                msg_id=self.main.get_update_msg_id(chat_id),
                delay=wait,
            )
        except Exception:
            self._logger.exception("Caught an exception in fileList")

    ############################################################################################
    def fileDetails(self, pathHash, page, cmd, fileHash, chat_id, from_id, wait=0):
        dest, path, file = self.find_file_by_hash(fileHash)
        self.tmpFileHash = ""
        meta = self.main._file_manager.get_metadata(dest, path)
        msg = f"{get_emoji('info')} <b>File information</b>\n\n"
        msg += f"{get_emoji('name')} <b>Name:</b> {path}"
        try:
            msg += f"\n{get_emoji('calendar')} <b>Uploaded:</b> " + datetime.datetime.fromtimestamp(
                file["date"]
            ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            self._logger.exception("Caught an exception in get upload time")

        self._logger.debug(f"val : {file}")
        self._logger.debug(f"meta : {meta}")
        try:
            if file.get("history"):
                HistList = file["history"]
                HistList.sort(key=lambda x: x["timestamp"], reverse=True)
                try:
                    if HistList[0]["success"]:
                        msg += f"\n{get_emoji('hooray')} <b>Number of Print:</b> {len(file['history'])}"
                    else:
                        msg += f"\n{get_emoji('warning')} <b>Number of Print:</b> {len(file['history'])}"
                except Exception:
                    msg += f"\n{get_emoji('file')} <b>Number of Print:</b> {len(file['history'])}"
            else:
                msg += f"\n{get_emoji('new')} <b>Number of Print:</b> 0"
        except Exception:
            msg += f"\n{get_emoji('file')} <b>Number of Print:</b> 0"

        msg += f"\n{get_emoji('filesize')} <b>Size:</b> {self.formatSize(file['size'])}"
        filaLen = 0
        if "analysis" in meta:
            if "filament" in meta["analysis"]:
                msg += f"\n{get_emoji('filament')} <b>Filament:</b> "
                filament = meta["analysis"]["filament"]
                if len(filament) == 1 and "length" in filament["tool0"]:
                    msg += self.formatFilament(filament["tool0"])
                    filaLen += float(filament["tool0"]["length"])
                else:
                    for key in sorted(filament):
                        if "length" in filament[key]:
                            msg += f"\n      {key}: {self.formatFilament(filament[key])}"
                            filaLen += float(filament[key]["length"])
            if "estimatedPrintTime" in meta["analysis"]:
                msg += f"\n{get_emoji('stopwatch')} <b>Print Time:</b> " + self.formatFuzzyPrintTime(
                    meta["analysis"]["estimatedPrintTime"]
                )
                printTime = meta["analysis"]["estimatedPrintTime"]

                try:
                    time_finish = self.main.calculate_ETA(printTime)
                    msg += f"\n{get_emoji('finish')} <b>Completed Time:</b> {time_finish}"
                except Exception:
                    self._logger.exception("Caught an exception calculating ETA")

                if self.main._plugin_manager.get_plugin("cost", True):
                    if printTime and filaLen != 0:
                        try:
                            cpH = self.main._settings.global_get_float(["plugins", "cost", "cost_per_time"])
                            cpM = self.main._settings.global_get_float(["plugins", "cost", "cost_per_length"])
                            curr = self.main._settings.global_get(["plugins", "cost", "currency"])
                            try:
                                curr = curr
                                msg += (
                                    f"\n{get_emoji('cost')} <b>Cost:</b> {curr}"
                                    + f"{filaLen / 1000 * cpM + printTime / 3600 * cpH:.02f} "
                                )
                            except Exception:
                                self._logger.exception("Caught an exception the cost function in decode")
                                msg += f"\n{get_emoji('cost')} <b>Cost:</b> -"
                        except Exception:
                            self._logger.exception("Caught an exception the cost function on get")
                            msg += f"\n{get_emoji('cost')} <b>Cost:</b> -"
                    else:
                        msg += f"\n{get_emoji('cost')} <b>Cost:</b> -"

        # will try to get the image from the thumbnail
        # will have to upload to somewhere to get internet url
        try:
            api_key = self.main._settings.get(["imgbbApiKey"])
            self._logger.info(f"get thumbnail url for path={path}")
            meta = self.main._file_manager.get_metadata(octoprint.filemanager.FileDestinations.LOCAL, path)

            if "thumbnail" in meta:
                imgUrl = meta["thumbnail"]
            else:
                imgUrl = None

            if api_key != "" and imgUrl is not None:
                imgUrl = f"http://localhost:{self.port}/{imgUrl}"
                r = requests.get(imgUrl)

                if r.status_code >= 300:
                    thumbnail_data = None
                else:
                    thumbnail_data = r.content
                if thumbnail_data is not None:
                    url = "https://api.imgbb.com/1/upload"
                    payload = {
                        "key": api_key,
                        "image": base64.b64encode(thumbnail_data),
                    }
                    res = requests.post(url, payload)
                    if res.status_code < 300:
                        test = res.json()
                        msg = f"<a href='{test['data']['url']}' >&#8199;</a>\n{msg}"
        except Exception:
            self._logger.exception("Caught an exception getting the thumbnail")

        keyPrint = [f"{get_emoji('play')} Print", f"/print_{fileHash}"]
        keyDetails = [
            f"{get_emoji('search')} Details",
            f"{cmd}_{pathHash}|{page}|{fileHash}|inf",
        ]
        keyDownload = [
            f"{get_emoji('download')} Download",
            f"{cmd}_{pathHash}|{page}|{fileHash}|dl",
        ]
        keyMove = [
            f"{get_emoji('cut')} Move",
            f"{cmd}_{pathHash}|{page}|{fileHash}|m",
        ]
        keyCopy = [
            f"{get_emoji('copy')} Copy",
            f"{cmd}_{pathHash}|{page}|{fileHash}|c",
        ]
        keyDelete = [
            f"{get_emoji('delete')} Delete",
            f"{cmd}_{pathHash}|{page}|{fileHash}|d",
        ]
        keyBack = [
            f"{get_emoji('back')} Back",
            f"{cmd}_{pathHash}|{page}",
        ]
        keysRow = []
        keys = []
        if self.main.is_command_allowed(chat_id, from_id, "/print"):
            keysRow.append(keyPrint)
        keysRow.append(keyDetails)
        keys.append(keysRow)
        keysRow = []
        if self.main.is_command_allowed(chat_id, from_id, "/files"):
            keysRow.append(keyMove)
            keysRow.append(keyCopy)
            keysRow.append(keyDelete)
            keys.append(keysRow)
            keysRow = []
            if self.dirHashDict[pathHash].split("/")[0] == octoprint.filemanager.FileDestinations.LOCAL:
                keysRow.append(keyDownload)
        keysRow.append(keyBack)
        keys.append(keysRow)
        self.main.send_msg(
            msg,
            chatID=chat_id,
            markup="HTML",
            responses=keys,
            msg_id=self.main.get_update_msg_id(chat_id),
            delay=wait,
        )

    ############################################################################################
    def fileOption(self, loc, page, cmd, hash, opt, chat_id, from_id):
        if opt != "m_m" and opt != "c_c" and not opt.startswith("s"):
            dest, path, file = self.find_file_by_hash(hash)
            meta = self.main._file_manager.get_metadata(dest, path)
        if opt.startswith("inf"):
            msg = f"{get_emoji('info')} <b>Detailed File information</b>\n\n"
            msg += f"{get_emoji('name')} <b>Name:</b> {path}"
            msg += f"\n {get_emoji('filesize')} <b>Size:</b> {self.formatSize(file['size'])}"
            msg += f"\n {get_emoji('calendar')} <b>Uploaded:</b> " + datetime.datetime.fromtimestamp(
                file["date"]
            ).strftime("%Y-%m-%d %H:%M:%S")
            filaLen = 0
            if "analysis" in meta:
                if "filament" in meta["analysis"]:
                    msg += f"\n{get_emoji('filament')} <b>Filament:</b> "
                    filament = meta["analysis"]["filament"]
                    if len(filament) == 1 and "length" in filament["tool0"]:
                        msg += self.formatFilament(filament["tool0"])
                        filaLen += float(filament["tool0"]["length"])
                    else:
                        for key in sorted(filament):
                            if "length" in filament[key]:
                                msg += f"\n      {key}: {self.formatFilament(filament[key])}"
                                filaLen += float(filament[key]["length"])
                if "estimatedPrintTime" in meta["analysis"]:
                    msg += f"\n {get_emoji('stopwatch')} <b>Print Time:</b> " + self.formatFuzzyPrintTime(
                        meta["analysis"]["estimatedPrintTime"]
                    )
                    printTime = meta["analysis"]["estimatedPrintTime"]

                    try:
                        time_finish = self.main.calculate_ETA(printTime)
                        msg += f"\n{get_emoji('finish')} <b>Completed Time:</b> {time_finish}"
                    except Exception:
                        self._logger.exception("Caught an exception calculating ETA")

                    if self.main._plugin_manager.get_plugin("cost", True):
                        if printTime and filaLen != 0:
                            try:
                                cpH = self.main._settings.global_get_float(["plugins", "cost", "cost_per_time"])
                                cpM = self.main._settings.global_get_float(["plugins", "cost", "cost_per_length"])
                                curr = self.main._settings.global_get(["plugins", "cost", "currency"])
                                try:
                                    curr = curr
                                    msg += (
                                        f"\n{get_emoji('cost')} <b>Cost:</b> "
                                        f"{curr}{((filaLen / 1000) * cpM + (printTime / 3600) * cpH):.2f} "
                                    )
                                except Exception:
                                    self._logger.exception("An Exception the cost function in decode")
                                    msg += f"\n{get_emoji('cost')} <b>Cost:</b> -"
                                self._logger.debug("AF TRY")
                            except Exception:
                                self._logger.exception("Caught an exception the cost function on get")
                                msg += f"\n{get_emoji('cost')} <b>Cost:</b> -"
                        else:
                            msg += f"\n{get_emoji('cost')} <b>Cost:</b> -"

            if "statistics" in meta:
                if "averagePrintTime" in meta["statistics"]:
                    msg += "\n<b>Average Print Time:</b>"
                    for avg in meta["statistics"]["averagePrintTime"]:
                        prof = self.main._printer_profile_manager.get(avg)
                        msg += (
                            f"\n      {prof['name']}: "
                            f"{self.formatDuration(meta['statistics']['averagePrintTime'][avg])}"
                        )
                if "lastPrintTime" in meta["statistics"]:
                    msg += "\n<b>Last Print Time:</b>"
                    for avg in meta["statistics"]["lastPrintTime"]:
                        prof = self.main._printer_profile_manager.get(avg)
                        msg += (
                            "\n      "
                            + prof["name"]
                            + ": "
                            + self.formatDuration(meta["statistics"]["lastPrintTime"][avg])
                        )
            if "history" in meta:
                if len(meta["history"]) > 0:
                    msg += "\n\n<b>Print History:</b> "
                    for hist in meta["history"]:
                        if "timestamp" in hist:
                            msg += "\n      Timestamp: " + datetime.datetime.fromtimestamp(hist["timestamp"]).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        if "printTime" in hist:
                            msg += "\n      Print Time: " + self.formatDuration(hist["printTime"])
                        if "printerProfile" in hist:
                            prof = self.main._printer_profile_manager.get(hist["printerProfile"])
                            msg += f"\n      Printer Profile: {prof['name']}"
                        if "success" in hist:
                            if hist["success"]:
                                msg += "\n      Successful printed"
                            else:
                                msg += "\n      Print failed"
                        msg += "\n"
            self.main.send_msg(
                msg,
                chatID=chat_id,
                responses=[
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{cmd}_{loc}|{page}|{hash}",
                        ]
                    ]
                ],
                msg_id=self.main.get_update_msg_id(chat_id),
                markup="HTML",
            )
        elif opt.startswith("dl"):
            mb = float(file["size"]) / 1024 / 1024
            if mb > 50:
                self.main.send_msg(
                    f"{get_emoji('warning')} {path} is too big (>50MB) to download!",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
                self.fileDetails(loc, page, cmd, hash, chat_id, from_id, wait=3)
            else:
                try:
                    self.main.send_file(chat_id, self.main._file_manager.path_on_disk(dest, path), "")
                except Exception:
                    self._logger.exception(f"Caught an exception sending a file to {chat_id}")
                    self.main.send_msg(
                        f"{get_emoji('warning')} An error occurred sending your file. Please check logs.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )

        elif opt.startswith("m"):
            msg_id = self.main.get_update_msg_id(chat_id)
            if opt == "m_m":
                destM, pathM, fileM = self.find_file_by_hash(self.tmpFileHash)
                targetPath = self.dirHashDict[hash]
                cpRes = self.fileCopyMove(destM, "move", pathM, "/".join(targetPath.split("/")[1:]))
                self._logger.debug(f"OUT MOVE: {cpRes}")
                if cpRes == "GOOD":
                    self.main.send_msg(
                        f"{get_emoji('info')} File {pathM} moved",
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileList(loc, page, cmd, chat_id, wait=3)
                else:
                    self.main.send_msg(
                        f"{get_emoji('warning')} FAILED: Move file {pathM}\nReason: {cpRes}",
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileDetails(loc, page, cmd, self.tmpFileHash, chat_id, from_id, wait=3)
            else:
                keys = [
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{cmd}_{loc}|{page}|{hash}",
                        ]
                    ]
                ]
                self.tmpFileHash = hash
                for key, val in sorted(list(self.dirHashDict.items()), key=operator.itemgetter(1)):
                    keys.append(
                        [
                            [
                                f"{get_emoji('folder')} {self.dirHashDict[key]}",
                                f"{cmd}_{loc}|{page}|{key}|m_m",
                            ]
                        ]
                    )
                self.main.send_msg(
                    f"{get_emoji('question')} *Choose destination to move file*",
                    chatID=chat_id,
                    responses=keys,
                    msg_id=msg_id,
                    markup="Markdown",
                )

        elif opt.startswith("c"):
            msg_id = self.main.get_update_msg_id(chat_id)
            if opt == "c_c":
                destM, pathM, fileM = self.find_file_by_hash(self.tmpFileHash)
                targetPath = self.dirHashDict[hash]
                cpRes = self.fileCopyMove(destM, "copy", pathM, "/".join(targetPath.split("/")[1:]))
                if cpRes == "GOOD":
                    self.main.send_msg(
                        f"{get_emoji('info')} File {pathM} copied",
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileList(loc, page, cmd, chat_id, wait=3)
                else:
                    self.main.send_msg(
                        f"{get_emoji('warning')} FAILED: Copy file {pathM}\nReason: {cpRes}",
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileDetails(loc, page, cmd, self.tmpFileHash, chat_id, from_id, wait=3)
            else:
                keys = [
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{cmd}_{loc}|{page}|{hash}",
                        ]
                    ]
                ]
                self.tmpFileHash = hash
                for key, val in sorted(list(self.dirHashDict.items()), key=operator.itemgetter(1)):
                    keys.append(
                        [
                            [
                                f"{get_emoji('folder')} {self.dirHashDict[key]}",
                                f"{cmd}_{loc}|{page}|{key}|c_c",
                            ]
                        ]
                    )
                self.main.send_msg(
                    f"{get_emoji('question')} *Choose destination to copy file*",
                    chatID=chat_id,
                    responses=keys,
                    msg_id=msg_id,
                    markup="Markdown",
                )

        elif opt.startswith("d"):
            msg_id = self.main.get_update_msg_id(chat_id)
            if opt == "d_d":
                delRes = self.fileDelete(dest, path)
                if delRes == "GOOD":
                    self.main.send_msg(
                        f"{get_emoji('info')} File {path} deleted",
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileList(loc, page, cmd, chat_id, wait=3)
                else:
                    self.main.send_msg(
                        f"{get_emoji('warning')} FAILED: Delete file {path}\nReason: {delRes}",
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileList(loc, page, cmd, chat_id, wait=3)
            else:
                keys = [
                    [
                        [
                            f"{get_emoji('check')} Yes",
                            f"{cmd}_{loc}|{page}|{hash}|d_d",
                        ],
                        [
                            f"{get_emoji('cancel')} No",
                            f"{cmd}_{loc}|{page}|{hash}",
                        ],
                    ]
                ]
                self.main.send_msg(
                    f"{get_emoji('warning')} Delete {path} ?",
                    chatID=chat_id,
                    responses=keys,
                    msg_id=msg_id,
                )
        elif opt.startswith("s"):
            if opt == "s_n":
                self.main._settings.set_boolean(["fileOrder"], False)
                self.fileList(loc, page, cmd, chat_id)
            elif opt == "s_d":
                self.main._settings.set_boolean(["fileOrder"], True)
                self.fileList(loc, page, cmd, chat_id)
            else:
                keys = [
                    [
                        [
                            f"{get_emoji('name')} By name",
                            f"{cmd}_{loc}|{page}|{hash}|s_n",
                        ],
                        [
                            f"{get_emoji('calendar')} By date",
                            f"{cmd}_{loc}|{page}|{hash}|s_d",
                        ],
                    ],
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{cmd}_{loc}|{page}",
                        ]
                    ],
                ]
                self.main.send_msg(
                    f"{get_emoji('question')} *Choose sorting order of files*",
                    chatID=chat_id,
                    markup="Markdown",
                    responses=keys,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )

    ### From filemanager plugin - https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
    ############################################################################################
    def fileCopyMove(self, target, command, source, destination):
        from octoprint.server.api.files import _verifyFileExists, _verifyFolderExists

        if not _verifyFileExists(target, source) and not _verifyFolderExists(target, source):
            return "Source does not exist"

        if _verifyFolderExists(target, destination):
            path, name = self.main._file_manager.split_path(target, source)
            destination = self.main._file_manager.join_path(target, destination, name)

        if _verifyFileExists(target, destination) or _verifyFolderExists(target, destination):
            return "Destination does not exist"

        if command == "copy":
            if self.main._file_manager.file_exists(target, source):
                self.main._file_manager.copy_file(target, source, destination)
            elif self.main._file_manager.folder_exists(target, source):
                self.main._file_manager.copy_folder(target, source, destination)
        elif command == "move":
            from octoprint.server.api.files import _isBusy

            if _isBusy(target, source):
                return "You can't move a file while it is in use"

            # deselect the file if it's currently selected
            from octoprint.server.api.files import _getCurrentFile

            currentOrigin, currentFilename = _getCurrentFile()
            if currentFilename is not None and source == currentFilename:
                self.main._printer.unselect_file()

            if self.main._file_manager.file_exists(target, source):
                self.main._file_manager.move_file(target, source, destination)
            elif self.main._file_manager.folder_exists(target, source):
                self.main._file_manager.move_folder(target, source, destination)
        return "GOOD"

    ### From filemanager plugin - https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
    ############################################################################################
    def fileDelete(self, target, source):
        # prohibit deleting or moving files that are currently in use
        from octoprint.server.api.files import (
            _getCurrentFile,
            _isBusy,
            _verifyFileExists,
            _verifyFolderExists,
        )

        currentOrigin, currentFilename = _getCurrentFile()

        if _verifyFileExists(target, source):
            from octoprint.server.api.files import _isBusy

            if _isBusy(target, source):
                return "Trying to delete a file that is currently in use"

            # deselect the file if it's currently selected
            if currentFilename is not None and source == currentFilename:
                self.main._printer.unselect_file()

            # delete it
            if target == octoprint.filemanager.FileDestinations.SDCARD:
                self.main._printer.delete_sd_file(source)
            else:
                self.main._file_manager.remove_file(target, source)
        elif _verifyFolderExists(target, source):
            if target not in [octoprint.filemanager.FileDestinations.LOCAL]:
                return "Unknown target"

            folderpath = source
            if _isBusy(target, folderpath):
                return "Trying to delete a folder that contains a file that is currently in use"

            # deselect the file if it's currently selected
            if currentFilename is not None and self.main._file_manager.file_in_path(
                target, folderpath, currentFilename
            ):
                self.main._printer.unselect_file()

            # delete it
            self.main._file_manager.remove_folder(target, folderpath)
        return "GOOD"

    ############################################################################################
    def generate_dir_hash_dict(self):
        try:
            self.dirHashDict = {}
            tree = self.main._file_manager.list_files(recursive=True)
            for key in tree:
                self.dirHashDict.update({str(self.hashMe(f"{key}/", 8)): f"{key}/"})
                self.dirHashDict.update(self.generate_dir_hash_dict_recursively(tree[key], f"{key}/"))
            self._logger.debug(f"{self.dirHashDict}")
        except Exception:
            self._logger.exception("Caught an exception in generate_dir_hash_dict")

    ############################################################################################
    def generate_dir_hash_dict_recursively(self, tree, loc):
        try:
            myDict = {}
            for key in tree:
                if tree[key]["type"] == "folder":
                    myDict.update({self.hashMe(f"{loc + key}/", 8): f"{loc + key}/"})
                    self.dirHashDict.update(
                        self.generate_dir_hash_dict_recursively(tree[key]["children"], f"{loc + key}/")
                    )
        except Exception:
            self._logger.exception("Caught an exception in generate_dir_hash_dict_recursively")
        return myDict

    ############################################################################################
    def find_file_by_hash(self, hash):
        try:
            tree = self.main._file_manager.list_files(recursive=True)
            for key in tree:
                result, file = self.find_file_by_hash_recursively(tree[key], hash)
                if result is not None:
                    return key, result, file
        except Exception:
            self._logger.exception("Caught an exception in find_file_by_hash")
        return None, None, None

    ############################################################################################
    def find_file_by_hash_recursively(self, tree, hash, base=""):
        for key in tree:
            if tree[key]["type"] == "folder":
                result, file = self.find_file_by_hash_recursively(tree[key]["children"], hash, base=f"{base + key}/")
                if result is not None:
                    return result, file
                continue
            if self.hashMe(base + tree[key]["name"]).startswith(hash):
                return base + key, tree[key]
        return None, None

    ############################################################################################
    # CONTROL HELPERS
    ############################################################################################
    def get_controls_recursively(self, tree=None, base="", first=""):
        array = []
        if tree is None:
            tree = self.main._settings.global_get(["controls"])
        for key in tree:
            try:
                if type(key) is type({}):
                    keyName = str(key["name"]) if "name" in key else ""
                    if base == "":
                        first = f" {keyName}"
                    if "children" in key:
                        array.extend(self.get_controls_recursively(key["children"], f"{base} {keyName}", first))
                    elif (
                        ("commands" in key or "command" in key or "script" in key)
                        and "regex" not in key
                        and "input" not in key
                    ):
                        newKey = {}
                        if "script" in key:
                            newKey["script"] = True
                            command = key["script"]
                        else:
                            command = key["command"] if "command" in key else key["commands"]
                        newKey["name"] = f"{base.replace(first, '')} {keyName}"
                        newKey["hash"] = self.hashMe(f"{base} {keyName}{command}", 6)
                        newKey["command"] = command
                        if "confirm" in key:
                            newKey["confirm"] = key["confirm"]
                        array.append(newKey)
            except Exception:
                self._logger.exception("Caught an exception in get key from tree")
        return array

    ############################################################################################
    def hashMe(self, text, length=32):
        try:
            return hashlib.md5(text.encode()).hexdigest()[0:length]
        except Exception:
            self._logger.exception("Caught an exception in hashMe")
            return ""

    ############################################################################################
    # CONNECTION HELPERS
    ############################################################################################
    def ConSettings(self, chat_id, parameter):
        if parameter:
            if parameter[0] == "p":
                self.ConPort(chat_id, parameter[1:], "s")
            elif parameter[0] == "b":
                self.ConBaud(chat_id, parameter[1:], "s")
            elif parameter[0] == "pr":
                self.ConProfile(chat_id, parameter[1:], "s")
            elif parameter[0] == "a":
                self.ConAuto(chat_id, parameter[1:])
        else:
            con = octoprint.printer.get_connection_options()
            profile = self.main._printer_profile_manager.get_default()
            msg = f"{get_emoji('settings')} Default connection settings \n\n"
            msg += f"*Port:* {con['portPreference']}"
            msg += f"\n*Baud:* {con['baudratePreference'] if con['baudratePreference'] else 'AUTO'}"
            msg += f"\n*Profile:* {profile['name']}"
            msg += f"\n*AutoConnect:* {con['autoconnect']}"
            self.main.send_msg(
                msg,
                responses=[
                    [
                        [f"{get_emoji('port')} Port", "/con_s|p"],
                        [f"{get_emoji('speed')} Baud", "/con_s|b"],
                        [
                            f"{get_emoji('profile')} Profile",
                            "/con_s|pr",
                        ],
                        [f"{get_emoji('lamp')} Auto", "/con_s|a"],
                    ],
                    [
                        [
                            f"{get_emoji('back')} Back",
                            "/con_back",
                        ]
                    ],
                ],
                chatID=chat_id,
                markup="Markdown",
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def ConPort(self, chat_id, parameter, parent):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set(["serial", "port"], parameter[0], force=True)
            self.main._settings.save()
            self.ConSettings(chat_id, [])
        else:
            con = octoprint.printer.get_connection_options()
            keys = []
            tmpKeys = [[f"{get_emoji('lamp')} AUTO", f"/con_{parent}|p|AUTO"]]
            i = 2
            for k in con["ports"]:
                tmpKeys.append(
                    [
                        f"{get_emoji('port')} {k}",
                        f"/con_{parent}|p|{k}",
                    ]
                )
                if i % 3 == 0:
                    keys.append(tmpKeys)
                    tmpKeys = []
                i += 1
            if len(tmpKeys) > 0 and len(tmpKeys) < 3:
                keys.append(tmpKeys)
            keys.append(
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"/con_{parent}",
                    ]
                ]
            )
            self.main.send_msg(
                f"{get_emoji('question')} Select default port.\nCurrent setting: {con['portPreference'] if con['portPreference'] else 'AUTO'}",
                responses=keys,
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def ConBaud(self, chat_id, parameter, parent):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set_int(["serial", "baudrate"], parameter[0], force=True)
            self.main._settings.save()
            self.ConSettings(chat_id, [])
        else:
            con = octoprint.printer.get_connection_options()
            keys = []
            tmpKeys = [[f"{get_emoji('lamp')} AUTO", f"/con_{parent}|b|0"]]
            i = 2
            for k in con["baudrates"]:
                tmpKeys.append(
                    [
                        f"{get_emoji('speed')} {k}",
                        f"/con_{parent}|b|{k}",
                    ]
                )
                if i % 3 == 0:
                    keys.append(tmpKeys)
                    tmpKeys = []
                i += 1
            if len(tmpKeys) > 0 and len(tmpKeys) < 3:
                keys.append(tmpKeys)
            keys.append(
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"/con_{parent}",
                    ]
                ]
            )
            self.main.send_msg(
                f"{get_emoji('question')} Select default baudrate.\nCurrent setting: {con['baudratePreference'] if con['baudratePreference'] else 'AUTO'}",
                responses=keys,
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def ConProfile(self, chat_id, parameter, parent):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set(["printerProfiles", "default"], parameter[0], force=True)
            self.main._settings.save()
            self.ConSettings(chat_id, [])
        else:
            con = self.main._printer_profile_manager.get_all()
            con2 = self.main._printer_profile_manager.get_default()
            keys = []
            tmpKeys = []
            i = 1
            for k in con:
                tmpKeys.append(
                    [
                        f"{get_emoji('profile')} {con[k]['name']}",
                        f"/con_{parent}|pr|{con[k]['id']}",
                    ]
                )
                if i % 3 == 0:
                    keys.append(tmpKeys)
                    tmpKeys = []
                i += 1
            if len(tmpKeys) > 0 and len(tmpKeys) < 3:
                keys.append(tmpKeys)
            keys.append(
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"/con_{parent}",
                    ]
                ]
            )
            self.main.send_msg(
                f"{get_emoji('question')} Select default profile.\nCurrent setting: {con2['name']}",
                responses=keys,
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def ConAuto(self, chat_id, parameter):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set_boolean(["serial", "autoconnect"], parameter[0], force=True)
            self.main._settings.save()
            self.ConSettings(chat_id, [])
        else:
            con = octoprint.printer.get_connection_options()
            keys = [
                [
                    [f"{get_emoji('check')} ON", "/con_s|a|true"],
                    [f"{get_emoji('cancel')} OFF", "/con_s|a|false"],
                ],
                [
                    [
                        f"{get_emoji('back')} Back",
                        "/con_s",
                    ]
                ],
            ]
            self.main.send_msg(
                f"{get_emoji('question')} AutoConnect on startup.\nCurrent setting: {con['autoconnect']}",
                responses=keys,
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def ConConnect(self, chat_id, parameter):
        if parameter:
            if parameter[0] == "a":
                self.conSettingsTemp.extend([None, None, None])
            elif parameter[0] == "d":
                self.conSettingsTemp.extend(
                    [
                        self.main._settings.global_get(["serial", "port"]),
                        self.main._settings.global_get(["serial", "baudrate"]),
                        self.main._printer_profile_manager.get_default(),
                    ]
                )
            elif parameter[0] == "p" and len(parameter) < 2:
                self.ConPort(chat_id, [], "c")
                return
            elif parameter[0] == "p":
                self.conSettingsTemp.append(parameter[1])
                self.ConBaud(chat_id, [], "c")
                return
            elif parameter[0] == "b":
                self.conSettingsTemp.append(parameter[1])
                self.ConProfile(chat_id, [], "c")
                return
            elif parameter[0] == "pr":
                self.conSettingsTemp.append(parameter[1])
            self.main.send_msg(
                f"{get_emoji('info')} Connecting...",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
            self.main._printer.connect(
                port=self.conSettingsTemp[0],
                baudrate=self.conSettingsTemp[1],
                profile=self.conSettingsTemp[2],
            )
            self.conSettingsTemp = []
            con = self.main._printer.get_current_connection()
            waitStates = [
                "Offline",
                "Detecting baudrate",
                "Connecting",
                "Opening serial port",
                "Detecting serial port",
                "Detecting serial connection",
                "Opening serial connection",
            ]
            while any(s in con[0] for s in waitStates):
                con = self.main._printer.get_current_connection()
            self._logger.debug(f"EXIT WITH: {con[0]}")

            if con[0] == "Operational":
                self.main.send_msg(
                    f"{get_emoji('check')} Connection established.",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            else:
                self.main.send_msg(
                    f"{get_emoji('warning')} Failed to start connection.\n\n{con[0]}",
                    chatID=chat_id,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
        else:
            keys = [
                [
                    [f"{get_emoji('lamp')} AUTO", "/con_c|a"],
                    [f"{get_emoji('star')} Default", "/con_c|d"],
                ],
                [
                    [f"{get_emoji('edit')} Manual", "/con_c|p"],
                    [
                        f"{get_emoji('back')} Back",
                        "/con_back",
                    ],
                ],
            ]
            self.main.send_msg(
                f"{get_emoji('question')} Select connection option.",
                chatID=chat_id,
                responses=keys,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    ############################################################################################
    def ConDisconnect(self, chat_id):
        self.main._printer.disconnect()
        self.main.send_msg(
            f"{get_emoji('info')} Printer disconnected.",
            chatID=chat_id,
            msg_id=self.main.get_update_msg_id(chat_id),
        )

    ############################################################################################
    # FORMAT HELPERS
    ############################################################################################
    def formatSize(self, bytes):
        # from octoprint/static/js/app/helpers.js transferred to python
        if not bytes:
            return "-"
        units = ["bytes", "KB", "MB", "GB"]
        for i in range(0, len(units)):
            if bytes < 1024:
                return f"{bytes:3.1f} {units[i]}"
            bytes = float(bytes) / 1024
        return f"{bytes:.1f}TB"

    ############################################################################################
    def formatFilament(self, filament):
        # from octoprint/static/js/app/helpers.js transferred to python
        if not filament or "length" not in filament:
            return "-"
        result = f"{float(filament['length']) / 1000:.02f} m"
        if "volume" in filament and filament["volume"]:
            result += f" / {float(filament['volume']):.02f} cm^3"
        return result

    ############################################################################################
    def formatDuration(self, seconds):
        if seconds is None:
            return "-"
        if seconds < 1:
            return "00:00:00"
        s = int(seconds) % 60
        m = (int(seconds) % 3600) / 60
        h = int(seconds) / 3600
        return "%02d:%02d:%02d" % (h, m, s)

    ############################################################################################
    def formatFuzzyPrintTime(self, totalSeconds):
        """
        From octoprint/static/js/app/helpers.js transferred to python

        Formats a print time estimate in a very fuzzy way.

        Accuracy decreases the higher the estimation is:

        * less than 30s: "a few seconds"
        * 30s to a minute: "less than a minute"
        * 1 to 30min: rounded to full minutes, above 30s is minute + 1 ("27 minutes", "2 minutes")
        * 30min to 40min: "40 minutes"
        * 40min to 50min: "50 minutes"
        * 50min to 1h: "1 hour"
        * 1 to 12h: rounded to half hours, 15min to 45min is ".5", above that hour + 1 ("4 hours", "2.5 hours")
        * 12 to 24h: rounded to full hours, above 30min is hour + 1, over 23.5h is "1 day"
        * Over a day: rounded to half days, 8h to 16h is ".5", above that days + 1 ("1 day", "4 days", "2.5 days")
        """

        if not totalSeconds or totalSeconds < 1:
            return "-"

        seconds = int(totalSeconds)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        replacements = {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "totalSeconds": totalSeconds,
        }

        text = "-"

        if days >= 1:
            # days
            if hours >= 16:
                replacements["days"] += 1
                if replacements["days"] == 1:
                    text = "%(days)d day"
                else:
                    text = "%(days)d days"
            elif 8 <= hours < 16:
                text = "%(days)d.5 days"
            else:
                if days == 1:
                    text = "%(days)d day"
                else:
                    text = "%(days)d days"
        elif hours >= 1:
            # only hours
            if hours < 12:
                if minutes < 15:
                    # less than .15 => .0
                    if hours == 1:
                        text = "%(hours)d hour"
                    else:
                        text = "%(hours)d hours"
                elif 15 <= minutes < 45:
                    # between .25 and .75 => .5
                    text = "%(hours)d.5 hours"
                else:
                    # over .75 => hours + 1
                    replacements["hours"] += 1
                    if replacements["hours"] == 1:
                        text = "%(hours)d hour"
                    else:
                        text = "%(hours)d hours"
            else:
                if hours == 23 and minutes > 30:
                    # over 23.5 hours => 1 day
                    text = "1 day"
                else:
                    if minutes > 30:
                        # over .5 => hours + 1
                        replacements["hours"] += 1
                    text = "%(hours)d hours"
        elif minutes >= 1:
            # only minutes
            if minutes < 2:
                if seconds < 30:
                    text = "a minute"
                else:
                    text = "2 minutes"
            elif minutes < 30:
                if seconds > 30:
                    replacements["minutes"] += 1
                text = "%(minutes)d minutes"
            elif minutes <= 40:
                text = "40 minutes"
            elif minutes <= 50:
                text = "50 minutes"
            else:
                text = "1 hour"
        else:
            # only seconds
            if seconds < 30:
                text = "a few seconds"
            else:
                text = "less than a minute"

        return text % replacements
