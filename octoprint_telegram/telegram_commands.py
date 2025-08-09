import base64
import datetime
import hashlib
import html
import operator
import socket
from itertools import islice

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
        self.port = self.main.port

        self.temp_notification_settings = {}
        self.temp_tune_rates = dict(feedrate=100, flowrate=100)
        self.temp_target_temps = {}
        self.temp_connection_settings = []

        self.dirHashDict = {}
        self.tmpFileHash = ""
        self._spoolManagerPluginImplementation = None

        self.commandDict = {
            "/status": {
                "cmd": self.cmdStatus,
                "desc": "Show current status",
            },
            "/togglepause": {
                "cmd": self.cmdTogglePause,
                "desc": "Pause or resume the current print",
            },
            "/home": {
                "cmd": self.cmdHome,
                "desc": "Home the printer's print head",
            },
            "/files": {
                "cmd": self.cmdFiles,
                "param": True,
                "desc": "List all available print files",
            },
            "/print": {
                "cmd": self.cmdPrint,
                "param": True,
                "desc": "Print the loaded file (confirmation required) or browse files",
            },
            "/tune": {
                "cmd": self.cmdTune,
                "param": True,
                "desc": "Adjust feed rate, flow, and temperatures",
            },
            "/ctrl": {
                "cmd": self.cmdCtrl,
                "param": True,
                "desc": "Activate custom OctoPrint controls",
            },
            "/con": {
                "cmd": self.cmdConnection,
                "param": True,
                "desc": "Connect or disconnect the printer",
            },
            "/sys": {
                "cmd": self.cmdSys,
                "param": True,
                "desc": "Run OctoPrint system commands",
            },
            "/abort": {
                "cmd": self.cmdAbort,
                "param": True,
                "desc": "Abort current print (confirmation required)",
            },
            "/power": {"cmd": self.cmdPower, "param": True, "desc": "Monitor and control power switches"},
            "/settings": {"cmd": self.cmdSettings, "param": True, "desc": "Show and change notification settings"},
            "/upload": {"cmd": self.cmdUpload, "desc": "Upload a file to OctoPrint library"},
            "/filament": {"cmd": self.cmdFilament, "param": True, "desc": "Manage filament spools"},
            "/user": {"cmd": self.cmdUser, "desc": "Get user information"},
            "/gcode": {
                "cmd": self.cmdGCode,
                "param": True,
                "desc": "Send G-code commands to the printer (use /gcode_XXX)",
            },
            "/gif": {
                "cmd": self.cmdGif,
                "desc": "Show GIFs from the webcams",
            },
            "/supergif": {
                "cmd": self.cmdSuperGif,
                "desc": "Show longer GIFs from the webcams",
            },
            "/photo": {
                "cmd": self.cmdPhoto,
                "desc": "Show photos from the webcams",
            },
            "/shutup": {
                "cmd": self.cmdShutup,
                "desc": "Disable automatic notifications until the next print ends",
            },
            "/dontshutup": {
                "cmd": self.cmdNShutup,
                "desc": "Make the bot talk again (opposite of /shutup)",
            },
            "/help": {"cmd": self.cmdHelp, "bind_none": True, "desc": "Show available commands"},
            "yes": {"cmd": self.cmdYes, "bind_none": True, "desc": "Confirm action"},
            "no": {"cmd": self.cmdNo, "bind_none": True, "desc": "Cancel action"},
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

    def cmdNo(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            "Maybe next time.",
            chatID=chat_id,
            msg_id=self.main.get_update_msg_id(chat_id),
            inline=False,
        )

    def cmdStatus(self, chat_id, from_id, cmd, parameter, user=""):
        if not self.main._printer.is_operational():
            with_image = self.main._settings.get_boolean(["image_not_connected"])
            with_gif = self.main._settings.get_boolean(["gif_not_connected"]) and self.main._settings.get(["send_gif"])
            self.main.send_msg(
                f"{get_emoji('warning')} Not connected to a printer. Use /con to connect.",
                chatID=chat_id,
                inline=False,
                with_image=with_image,
                with_gif=with_gif,
            )
        elif self.main._printer.is_printing():
            self.main.on_event("StatusPrinting", {}, chatID=chat_id)
        else:
            self.main.on_event("StatusNotPrinting", {}, chatID=chat_id)

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

    def cmdPhoto(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            f"{get_emoji('photo')} Here are your photo(s)",
            chatID=chat_id,
            with_image=True,
        )

    def cmdSettings(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "h":
                if len(params) > 1:
                    delta_str = params[1]
                    height = self.temp_notification_settings["notification_height"]

                    if delta_str.startswith(("+", "-")):
                        sign = 1 if delta_str.startswith("+") else -1
                        magnitude = 100 / (10 ** len(delta_str))
                        new_height = max(height + sign * magnitude, 0)
                        self.temp_notification_settings["notification_height"] = new_height

                    else:
                        self.main._settings.set_float(["notification_height"], height)
                        self.main._settings.save()
                        self.cmdSettings(chat_id, from_id, cmd, "back", user)
                        return

                msg = (
                    f"{get_emoji('height')} Set new height.\n"
                    f"Current: <b>{self.temp_notification_settings['notification_height']:.2f}mm</b>"
                )

                command_buttons = [
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
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            elif params[0] == "t":
                if len(params) > 1:
                    delta_str = params[1]
                    notification_time = self.temp_notification_settings["notification_time"]

                    if delta_str.startswith(("+", "-")):
                        sign = 1 if delta_str.startswith("+") else -1
                        magnitude = 100 / (10 ** len(delta_str))
                        new_notification_time = max(int(notification_time + sign * magnitude), 0)
                        self.temp_notification_settings["notification_time"] = new_notification_time
                    else:
                        self.main._settings.set_int(["notification_time"], notification_time)
                        self.main._settings.save()
                        self.cmdSettings(chat_id, from_id, cmd, "back", user)
                        return

                msg = (
                    f"{get_emoji('alarmclock')} Set new time.\n"
                    f"Current: <b>{self.temp_notification_settings['notification_time']}min</b>"
                )

                command_buttons = [
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
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            elif params[0] == "g":
                self.main._settings.set_boolean(["send_gif"], not self.main._settings.get_boolean(["send_gif"]))
                self.main._settings.save()
                self.cmdSettings(chat_id, from_id, cmd, "back", user)
                return
        else:
            notification_height = self.main._settings.get_float(["notification_height"])
            notification_time = self.main._settings.get_int(["notification_time"])
            send_gif = self.main._settings.get_boolean(["send_gif"])

            self.temp_notification_settings = dict(
                notification_height=notification_height, notification_time=notification_time
            )

            gif_txt = "Deactivate gif" if send_gif else "Activate gif"
            gif_emo = get_emoji("check" if send_gif else "cancel")

            msg = (
                f"{get_emoji('settings')} <b>Current notification settings are:</b>\n\n"
                f"{get_emoji('height')} Height: {notification_height:.2f}mm\n\n"
                f"{get_emoji('alarmclock')} Time: {notification_time:d}min\n\n"
                f"{get_emoji('video')} Gif is active: {gif_emo}"
            )

            command_buttons = [
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
                [[f"{get_emoji('cancel')} Close", "no"]],
            ]

            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""

            self.main.send_msg(
                msg,
                chatID=chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=msg_id,
            )

    def cmdAbort(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter == "stop":
            self.main._printer.cancel_print(user=user)
            self.main.send_msg(
                f"{get_emoji('info')} Aborting the print.",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
        else:
            if self.main._printer.is_printing() or self.main._printer.is_paused():
                self.main.send_msg(
                    f"{get_emoji('question')} Really abort the currently running print?",
                    responses=[
                        [
                            [
                                f"{get_emoji('check')} Stop print",
                                "/abort_stop",
                            ],
                            [f"{get_emoji('cancel')} Close", "no"],
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

    def cmdHome(self, chat_id, from_id, cmd, parameter, user=""):
        if self.main._printer.is_ready():
            msg = f"{get_emoji('home')} Homing."
            self.main._printer.home(["x", "y", "z"])
        else:
            msg = f"{get_emoji('warning')} I can't go home now."
        self.main.send_msg(msg, chatID=chat_id, inline=False)

    def cmdShutup(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.shut_up.add(str(chat_id))
        self.main.send_msg(
            f"{get_emoji('nonotify')} Okay, shutting up until the next print is finished.\n"
            f"Use /dontshutup to let me talk again before that.",
            chatID=chat_id,
            inline=False,
        )

    def cmdNShutup(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.shut_up.discard(str(chat_id))
        self.main.send_msg(
            f"{get_emoji('notify')} Yay, I can talk again.",
            chatID=chat_id,
            inline=False,
        )

    def cmdPrint(self, chat_id, from_id, cmd, parameter, user=""):
        if not self.main._printer.is_ready():
            self.main.send_msg(
                f"{get_emoji('warning')} Can't start a new print, printer is not ready. Printer status: {self.main._printer.get_state_string()}",
                chatID=chat_id,
            )
            return

        if parameter and len(parameter.split("|")) == 1:
            if parameter == "s":  # print the loaded file
                data = self.main._printer.get_current_data()
                if data["job"]["file"]["name"] is None:
                    self.main.send_msg(
                        f"{get_emoji('warning')} Uh oh... No file is selected for printing. Did you select one using /files?",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
                    return

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
            else:  # prepare print (load and ask for confirm)
                self._logger.debug(f"Looking for hash: {parameter}")
                destination, file, f = self.find_file_by_hash(parameter)
                if file is None:
                    msg = f"{get_emoji('warning')} I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /files again?"
                    self.main.send_msg(
                        msg,
                        chatID=chat_id,
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
                else:
                    self.main.send_msg(
                        f"{get_emoji('warning')} Uh oh... Problems on loading the file for print.",
                        chatID=chat_id,
                        msg_id=self.main.get_update_msg_id(chat_id),
                    )
        else:  # offer the already loaded file or open files listing
            data = self.main._printer.get_current_data()
            if data["job"]["file"]["name"] is not None:
                msg = (
                    f"{get_emoji('info')} The file {data['job']['file']['name']} is already loaded.\n\n"
                    f"{get_emoji('question')} What do you want to do?"
                )
                self.main.send_msg(
                    msg,
                    responses=[
                        [
                            [
                                f"{get_emoji('play')} Print it",
                                "/print_s",
                            ],
                            [
                                f"{get_emoji('folder')} List files",
                                "/files",
                            ],
                        ]
                    ],
                    chatID=chat_id,
                )
            else:
                self.cmdFiles(chat_id, from_id, cmd, parameter, user)

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

                    msg = f"{get_emoji('save')} <b>Select Storage</b>"

                    command_buttons = []
                    command_buttons.extend([([k, (f"{cmd}_{self.hashMe(k, 8)}/|0")] for k in storages)])
                    command_buttons.append([[f"{get_emoji('cancel')} Close", "no"]])

                    msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""

                    self.main.send_msg(
                        msg,
                        chatID=chat_id,
                        markup="HTML",
                        responses=command_buttons,
                        msg_id=msg_id,
                    )
        except Exception:
            self._logger.exception("Command failed")
            self.main.send_msg(
                f"{get_emoji('warning')} Command failed, please check log files",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    def cmdUpload(self, chat_id, from_id, cmd, parameter, user=""):
        self.main.send_msg(
            f"{get_emoji('info')} To upload a gcode file (also accept zip file), just send it to me.\nThe file will be stored in 'TelegramPlugin' folder.",
            chatID=chat_id,
        )

    def cmdSys(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "sys":
                if params[1] != "do":
                    msg = f"{get_emoji('question')} <b>{html.escape(params[1])}</b>\nExecute system command?"

                    command_buttons = [
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
                    ]

                    self.main.send_msg(
                        msg,
                        chatID=chat_id,
                        markup="HTML",
                        responses=command_buttons,
                        msg_id=self.main.get_update_msg_id(chat_id),
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

            keys.append([[f"{get_emoji('cancel')} Close", "no"]])
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)

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
                keys.append([[f"{get_emoji('cancel')} Close", "no"]])
            except Exception:
                self._logger.exception("An Exception in get list action")
            if empty:
                message += f"\n\n{get_emoji('warning')} No Printer Control Command found..."
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)

    def split_parameters(self, param_str: str, separator: str = "_") -> list[str]:
        """
        Splits a string into a list of parameters using the specified separator
        (default: underscore '_'), correctly handling escaped separators (e.g., '\\_').

        This function is useful to parse strings where parameters may contain the separator
        character, escaped to avoid splitting on them.

        Args:
            param_str (str): The input string to split.
            separator (str): The character to use as separator (default: '_').

        Returns:
            list[str]: The list of split and unescaped parameters.
        """
        params = []
        current = ""
        escaped = False
        for char in param_str:
            if escaped:
                current += char
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == separator:
                params.append(current)
                current = ""
            else:
                current += char
        params.append(current)
        return params

    def send_octoprint_api_command(self, plugin_id: str, command: str, parameters: dict = None, timeout: int = 5):
        """
        Sends a command to an OctoPrint plugin via the HTTP API.

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

        response = requests.post(
            f"http://localhost:{self.port}/api/plugin/{plugin_id}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": self.main._settings.global_get(["api", "key"]),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response

    def send_octoprint_api_get(self, plugin_id: str, parameters: dict = None, timeout: int = 5):
        """
        Sends a GET request to an OctoPrint plugin via the HTTP API.

        Args:
            plugin_id (str): The ID of the plugin to target.
            parameters (dict, optional): Query parameters to include in the request.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 5.

        Returns:
            requests.Response: The response object from the GET request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        response = requests.get(
            f"http://localhost:{self.port}/api/plugin/{plugin_id}",
            params=parameters or {},
            headers={
                "X-Api-Key": self.main._settings.global_get(["api", "key"]),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response

    def cmdPower(self, chat_id, from_id, cmd, parameter, user=""):
        supported_plugins = {
            "domoticz": "Domoticz",
            "gpiocontrol": "GPIO Control",
            "ikea_tradfri": "Ikea Tradfri",
            "octolight": "OctoLight",
            "octolightHA": "OctoLight HA",
            "octorelay": "OctoRelay",
            "orvibos20": "OrviboS20",
            "psucontrol": "PSU Control",
            "tasmota": "Tasmota",
            "tasmota_mqtt": "TasmotaMQTT",
            "tplinksmartplug": "TPLinkSmartplug",
            "tuyasmartplug": "TuyaSmartplug",
            "usbrelaycontrol": "USB Relay Control",
            "wemoswitch": "WemoSwitch",
            "wled": "WLED",
            "ws281x_led_status": "WS281x",
        }

        available_plugins = {
            plugin_id: plugin_name
            for plugin_id, plugin_name in supported_plugins.items()
            if self.main._plugin_manager.get_plugin(plugin_id, True)
        }

        if not available_plugins:
            message = (
                f"{get_emoji('warning')} No power manager plugin installed. "
                "Please install one of the following plugins:\n"
            )
            for plugin_id, plugin_name in supported_plugins.items():
                message += f"- <a href='https://plugins.octoprint.org/plugins/{html.escape(plugin_id)}/'>{html.escape(plugin_name)}</a>\n"

            self.main.send_msg(
                message,
                chatID=chat_id,
                markup="HTML",
            )

            return

        def get_plugs_data(plugin_id):
            """
            Retrieves information about all plugs managed by the specified power plugin.

            Args:
                plugin_id (str): Identifier of the power management plugin.

            Returns:
                List[Dict[str, Any]]: A list of plug dictionaries, each containing:
                    - "label" (str): Human-readable name for display.
                    - "is_on" (bool): Current power state.
                    - "data" (str): Internal identifier used by ON/OFF APIs, separated by "|".

            Raises:
                ValueError: If the specified plugin is not supported.
            """
            plugs_data = []

            if plugin_id == "domoticz":
                # Domoticz plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/jneilliii/OctoPrint-Domoticz/blob/a3e1d6fddbe6a8b09faf53f62e519f8499e4cc82/octoprint_domoticz/__init__.py#L147
                plugs = self.main._settings.global_get(["plugins", plugin_id, "arrSmartplugs"])
                for plug in plugs:
                    try:
                        ip = plug["ip"]
                        idx = plug["idx"]
                        username = plug.get("username", "")
                        password = plug.get("password", "")
                        passcode = plug.get("passcode", "")

                        is_on = False
                        try:
                            # Domoticz plugin has no API nor plugin functions for getting plug status, so below code is copied from the plugin code:
                            # https://github.com/jneilliii/OctoPrint-Domoticz/blob/a3e1d6fddbe6a8b09faf53f62e519f8499e4cc82/octoprint_domoticz/__init__.py#L241
                            str_url = f"{ip}/json.htm?type=command&param=getdevices&rid={idx}"
                            if passcode != "":
                                str_url = f"{str_url}&passcode={passcode}"
                            if username != "":
                                response = requests.get(str_url, auth=(username, password), timeout=10, verify=False)
                            else:
                                response = requests.get(str_url, timeout=10, verify=False)
                            is_on = response.json()["result"][0]["Status"].lower() == "on"
                        except Exception:
                            self._logger.exception(f"Caught an exception getting {plugin_id} plug status")

                        label = plug.get("label") or f"{ip}|{idx}"

                        escaped_ip = ip.replace("|", "\\|")
                        escaped_idx = idx.replace("|", "\\|")
                        data = f"{escaped_ip}|{escaped_idx}"

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "gpiocontrol":
                # Gpiocontrol plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/catgiggle/OctoPrint-GpioControl/blob/37f698e51ff02493d833f43e14e88bdf54cd8b37/octoprint_gpiocontrol/__init__.py#L129
                try:
                    statuses = self.send_octoprint_api_get(plugin_id).json()
                except Exception:
                    statuses = []
                    self._logger.exception(f"Caught an exception getting {plugin_id} plugs statuses")

                plugs = self.main._settings.global_get(["plugins", plugin_id, "gpio_configurations"])
                for index, configuration in enumerate(plugs):
                    try:
                        label = configuration["name"] or f"GPIO{configuration['pin']}"
                        is_on = index < len(statuses) and statuses[index].lower() == "on"
                        data = index

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "ikea_tradfri":
                # Ikea_tradfri plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/ralmn/OctoPrint-Ikea-tradfri/blob/4c19c3588e3a2a85c7d78ed047062fb8d3994876/octoprint_ikea_tradfri/__init__.py#L547
                plugs = self.main._settings.global_get(["plugins", plugin_id, "selected_devices"])
                for plug in plugs:
                    try:
                        is_on = False
                        try:
                            response = self.send_octoprint_api_command(plugin_id, "checkStatus", {"ip": plug["id"]})
                            is_on = response.json().get("currentState", "").lower() == "on"
                        except Exception:
                            self._logger.exception(f"Caught an exception getting {plugin_id} plug status")

                        label = plug.get("name") or plug["id"]
                        data = plug["id"]

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "octolight":
                is_on = False
                try:
                    response = self.send_octoprint_api_get(plugin_id)
                    is_on = response.json().get("state", False)
                except Exception:
                    self._logger.exception(f"Caught an exception getting {plugin_id} status")

                # Octolight is single plug, so label and data below are dummy
                label = available_plugins[plugin_id]
                data = plugin_id

                plugs_data.append({"label": label, "is_on": is_on, "data": data})

            elif plugin_id == "octolightHA":
                is_on = False
                try:
                    response = self.send_octoprint_api_get(plugin_id, dict(action="getState"))
                    is_on = response.json().get("state", False)
                except Exception:
                    self._logger.exception(f"Caught an exception getting {plugin_id} status")

                # OctolightHA is single plug, so label and data below are dummy
                label = available_plugins[plugin_id]
                data = plugin_id

                plugs_data.append({"label": label, "is_on": is_on, "data": data})

            elif plugin_id == "octorelay":
                response = self.send_octoprint_api_command(plugin_id, "listAllStatus")
                plugs = response.json()
                for plug in plugs:
                    try:
                        label = plug.get("name") or f"RELAY{plug['id']}"
                        is_on = plug["status"]
                        data = plug["id"]

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "orvibos20":
                # OrviboS20 plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/cprasmu/OctoPrint-OrviboS20/blob/a40d0ad4184e48781ff1ebc7fb108eba1e084ba8/octoprint_orvibos20/__init__.py#L500
                plugs = self.main._settings.global_get(["plugins", plugin_id, "arrSmartplugs"])
                for plug in plugs:
                    try:
                        is_on = False
                        try:
                            # OrviboS20 plugin has no API for getting plug status, so we need to use the plugin functions
                            plugin_module = self.main._plugin_manager.get_plugin(plugin_id, True)
                            is_on = plugin_module.Orvibo.discover(plug["ip"]).on
                        except Exception:
                            self._logger.exception(f"Caught an exception getting {plugin_id} plug status")

                        label = plug.get("label") or plug["ip"]
                        data = plug["ip"]

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "psucontrol":
                is_on = False
                try:
                    response = self.send_octoprint_api_command(plugin_id, "getPSUState")
                    is_on = response.json().get("isPSUOn", False)
                except Exception:
                    self._logger.exception(f"Caught an exception getting {plugin_id} status")

                # Psucontrol is single plug, so label and data below are dummy
                label = available_plugins[plugin_id]
                data = plugin_id

                plugs_data.append({"label": label, "is_on": is_on, "data": data})

            elif plugin_id == "tasmota":
                # Tasmota plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/jneilliii/OctoPrint-Tasmota/blob/49c7e01f4a077d0d650931fd91f3b63cfef780c2/octoprint_tasmota/__init__.py#L816
                plugs = self.main._settings.global_get(["plugins", plugin_id, "arrSmartplugs"])
                for plug in plugs:
                    try:
                        is_on = False
                        try:
                            response = self.send_octoprint_api_command(
                                plugin_id, "checkStatus", {"ip": plug["ip"], "idx": plug["idx"]}
                            )
                            is_on = response.json().get("currentState", "").lower() == "on"
                        except Exception:
                            self._logger.exception(f"Caught an exception getting {plugin_id} plug status")

                        label = plug.get("label") or f"{plug['ip']}|{plug['idx']}"

                        escaped_ip = plug["ip"].replace("|", "\\|")
                        escaped_idx = plug["idx"].replace("|", "\\|")
                        data = f"{escaped_ip}|{escaped_idx}"

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "tasmota_mqtt":
                response = self.send_octoprint_api_command(plugin_id, "getListPlug")
                plugs = response.json()
                for plug in plugs:
                    try:
                        is_on = plug.get("currentstate", "").lower() == "on"

                        label = plug.get("label") or f"{plug['topic']}|{plug['relayN']}"

                        escaped_topic = plug["topic"].replace("|", "\\|")
                        escaped_relay = plug["relayN"].replace("|", "\\|")
                        data = f"{escaped_topic}|{escaped_relay}"

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "tplinksmartplug":
                response = self.send_octoprint_api_command(plugin_id, "getListPlug")
                plugs = response.json()
                for plug in plugs:
                    try:
                        is_on = plug.get("currentState", "").lower() == "on"
                        label = plug.get("label") or plug["ip"]
                        data = plug["ip"]

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "tuyasmartplug":
                # Tuyasmartplug plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/ziirish/OctoPrint-TuyaSmartplug/blob/4344aeb6d9d59f4979d326a710656121d247e9af/octoprint_tuyasmartplug/__init__.py#L240
                plugs = self.main._settings.global_get(["plugins", plugin_id, "arrSmartplugs"])
                for plug in plugs:
                    try:
                        is_on = False
                        try:
                            # Tuyasmartplug plugin has no API for getting plug status, so we need to use the plugin functions
                            plugin_implementation = self.main._plugin_manager.plugins[plugin_id].implementation
                            is_on = plugin_implementation.is_turned_on(pluglabel=plug["label"])
                        except Exception:
                            self._logger.exception(f"Caught an exception getting {plugin_id} plug status")

                        label = plug["label"]
                        data = label

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "usbrelaycontrol":
                # Usbrelaycontrol plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/abudden/OctoPrint-USBRelayControl/blob/0f06bccc06107f2b76fe360fed63698472c483cc/octoprint_usbrelaycontrol/__init__.py#L135
                try:
                    statuses = self.send_octoprint_api_get(plugin_id).json()
                except Exception:
                    statuses = []
                    self._logger.exception(f"Caught an exception getting {plugin_id} plugs statuses")

                plugs = self.main._settings.global_get(["plugins", plugin_id, "usbrelay_configurations"])
                for index, configuration in enumerate(plugs):
                    try:
                        label = configuration["name"] or f"RELAY{configuration['relaynumber']}"
                        is_on = index < len(statuses) and statuses[index].lower() == "on"
                        data = index

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "wemoswitch":
                # Wemoswitch plugin has no API for getting plugs. Below code is copied from the plugin code:
                # https://github.com/jneilliii/OctoPrint-WemoSwitch/blob/70500edbff7eeda65efecc105f573e546cb8d661/octoprint_wemoswitch/__init__.py#L247
                plugs = self.main._settings.global_get(["plugins", plugin_id, "arrSmartplugs"])
                for plug in plugs:
                    try:
                        is_on = False
                        try:
                            # Wemoswitch plugin has no API for getting plug status, so we need to use the plugin functions
                            plugin_implementation = self.main._plugin_manager.plugins[plugin_id].implementation
                            chk = plugin_implementation.sendCommand("info", plug["ip"])
                            is_on = chk == 1 or chk == 8
                        except Exception:
                            self._logger.exception(f"Caught an exception getting {plugin_id} plug status")

                        label = plug["label"] or plug["ip"]
                        data = plug["ip"]

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            elif plugin_id == "wled":
                is_on = False
                try:
                    response = self.send_octoprint_api_get(plugin_id)
                    is_on = response.json().get("lights_on", False)
                except Exception:
                    self._logger.exception(f"Caught an exception getting {plugin_id} status")

                # Wled is single plug, so label and data below are dummy
                label = available_plugins[plugin_id]
                data = plugin_id

                plugs_data.append({"label": label, "is_on": is_on, "data": data})

            elif plugin_id == "ws281x_led_status":
                plugs_names = ["lights", "torch"]

                statuses = {}
                try:
                    statuses = self.send_octoprint_api_get(plugin_id).json()
                except Exception:
                    self._logger.exception(f"Caught an exception getting {plugin_id} status")

                for plug_name in plugs_names:
                    try:
                        label = f"{available_plugins[plugin_id]} {plug_name}"
                        is_on = statuses.get(f"{plug_name}_on", False)
                        data = plug_name

                        plugs_data.append({"label": label, "is_on": is_on, "data": data})
                    except Exception:
                        self._logger.exception(f"Caught an exception processing {plugin_id} plug data")

            else:
                raise ValueError(f"Plugin {plugin_id} not supported")

            return plugs_data

        if not parameter:
            # Command was /power, show plugs list

            message = f"{get_emoji('question')} Which plug do you want to manage?"

            plug_buttons = []
            for plugin_id in available_plugins:
                try:
                    for plug_data in get_plugs_data(plugin_id):
                        label = plug_data["label"]

                        is_on = plug_data["is_on"]
                        status_emoji = get_emoji("online" if is_on else "offline")

                        data = plug_data["data"]
                        command = cmd + "_" + plugin_id.replace("_", "\\_") + "_" + str(data).replace("_", "\\_")

                        plug_buttons.append([f"{status_emoji} {label}", command])
                except Exception:
                    self._logger.exception(f"Caught an exception getting {plugin_id} plugs")

            max_per_row = 3
            plug_button_rows = [plug_buttons[i : i + max_per_row] for i in range(0, len(plug_buttons), max_per_row)]
            command_buttons = plug_button_rows + [[[f"{get_emoji('cancel')} Close", "no"]]]

            self.main.send_msg(
                message,
                chatID=chat_id,
                responses=command_buttons,
                msg_id=self.main.get_update_msg_id(chat_id),
                markup="HTML",
            )

        else:
            splitted_parameters = self.split_parameters(parameter)
            plugin_id, plug_data, action = (splitted_parameters + [None] * 3)[:3]

            if plugin_id not in available_plugins:
                message = f"{get_emoji('attention')} Plugin {html.escape(plugin_id)} is not available!"
                command_buttons = [[[f"{get_emoji('back')} Back", cmd], [f"{get_emoji('cancel')} Close", "no"]]]
                self.main.send_msg(
                    message,
                    chatID=chat_id,
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="HTML",
                )
                return

            if action is None:
                # Command was /power_plugin\_id_plug\_data, show plug status and ask for action

                plugs = get_plugs_data(plugin_id)
                selected_plug = None

                selected_plug = next((plug for plug in plugs if str(plug["data"]) == plug_data), None)

                if selected_plug is None:
                    message = f"{get_emoji('attention')} Selected plug not found!"
                    command_buttons = [[[f"{get_emoji('back')} Back", cmd], [f"{get_emoji('cancel')} Close", "no"]]]
                    self.main.send_msg(
                        message,
                        chatID=chat_id,
                        responses=command_buttons,
                        msg_id=self.main.get_update_msg_id(chat_id),
                        markup="HTML",
                    )
                    return

                label = selected_plug["label"]
                is_on = selected_plug["is_on"]
                status_text = "ON" if is_on else "OFF"
                status_emoji = get_emoji("online" if is_on else "offline")

                message = (
                    f"{get_emoji('info')} Plug {html.escape(label)} is {status_emoji} {status_text}.\n"
                    f"{get_emoji('question')} What do you want to do?"
                )

                original_command = f"{cmd}_{parameter}"
                command_buttons = [
                    [
                        [f"{get_emoji('online')} Turn ON", f"{original_command}_on"],
                        [f"{get_emoji('offline')} Turn OFF", f"{original_command}_off"],
                    ],
                    [[f"{get_emoji('back')} Back", cmd], [f"{get_emoji('cancel')} Close", "no"]],
                ]

                self.main.send_msg(
                    message,
                    chatID=chat_id,
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="HTML",
                )
            else:
                # Command was /power_plugin\_id_plug\_data_action, execute action

                if action not in ("on", "off"):
                    message = f"{get_emoji('attention')} Action not supported!"
                else:
                    try:
                        if plugin_id == "domoticz":
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"

                            ip, idx = self.split_parameters(plug_data, "|")

                            selected_plug = None
                            plugs = self.main._settings.global_get(["plugins", plugin_id, "arrSmartplugs"])
                            for plug in plugs:
                                if plug.get("ip") == ip and plug.get("idx") == idx:
                                    selected_plug = plug
                                    break
                            if not selected_plug:
                                raise RuntimeError(f"Plug {plug_data} not found")

                            username = selected_plug["username"]
                            password = selected_plug["password"]
                            passcode = selected_plug["passcode"]

                            self.send_octoprint_api_command(
                                plugin_id,
                                command,
                                {
                                    "ip": ip,
                                    "idx": idx,
                                    "username": username,
                                    "password": password,
                                    "passcode": passcode,
                                },
                            )
                        elif plugin_id == "gpiocontrol":
                            if action == "off":
                                command = "turnGpioOff"
                            elif action == "on":
                                command = "turnGpioOn"
                            self.send_octoprint_api_command(plugin_id, command, {"id": plug_data})
                        elif plugin_id in {"ikea_tradfri", "orvibos20", "tplinksmartplug", "wemoswitch"}:
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"
                            self.send_octoprint_api_command(plugin_id, command, {"ip": plug_data})
                        elif plugin_id == "octolight":
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"
                            self.send_octoprint_api_command(plugin_id, command)
                        elif plugin_id == "octolightHA":
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"
                            self.send_octoprint_api_get(plugin_id, dict(action=command))
                        elif plugin_id == "octorelay":
                            self.send_octoprint_api_command(
                                plugin_id, "update", {"subject": plug_data, "target": action == "on"}
                            )
                        elif plugin_id == "psucontrol":
                            if action == "off":
                                command = "turnPSUOff"
                            elif action == "on":
                                command = "turnPSUOn"
                            self.send_octoprint_api_command(plugin_id, command)
                        elif plugin_id == "tasmota":
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"
                            ip, idx = self.split_parameters(plug_data, "|")
                            self.send_octoprint_api_command(plugin_id, command, {"ip": ip, "idx": idx})
                        elif plugin_id == "tasmota_mqtt":
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"
                            topic, relay_n = self.split_parameters(plug_data, "|")
                            self.send_octoprint_api_command(plugin_id, command, {"topic": topic, "relayN": relay_n})
                        elif plugin_id == "tuyasmartplug":
                            if action == "off":
                                command = "turnOff"
                            elif action == "on":
                                command = "turnOn"
                            self.send_octoprint_api_command(plugin_id, command, {"label": plug_data})
                        elif plugin_id == "usbrelaycontrol":
                            if action == "off":
                                command = "turnUSBRelayOff"
                            elif action == "on":
                                command = "turnUSBRelayOn"
                            self.send_octoprint_api_command(plugin_id, command, {"id": plug_data})
                        elif plugin_id == "wled":
                            if action == "off":
                                command = "lights_off"
                            elif action == "on":
                                command = "lights_on"
                            self.send_octoprint_api_command(plugin_id, command)
                        elif plugin_id == "ws281x_led_status":
                            if action == "off":
                                command = f"{plug_data}_off"
                            elif action == "on":
                                command = f"{plug_data}_on"
                            self.send_octoprint_api_command(plugin_id, command)
                        else:
                            raise ValueError(f"Plugin {plugin_id} not supported")

                        message = f"{get_emoji('check')} Command sent!"
                    except Exception:
                        self._logger.exception(f"Caught an exception sending action to {plugin_id}")
                        message = f"{get_emoji('attention')} Something went wrong!"

                original_command = f"{cmd}_{parameter.rsplit('_', 1)[0]}"
                command_buttons = [
                    [[f"{get_emoji('back')} Back", original_command], [f"{get_emoji('cancel')} Close", "no"]],
                ]

                self.main.send_msg(
                    message,
                    chatID=chat_id,
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                    markup="HTML",
                )

    def cmdUser(self, chat_id, from_id, cmd, parameter, user=""):
        chat_data = self.main._settings.get(["chats", chat_id])

        msg = (
            f"{get_emoji('info')} <b>Your user settings:</b>\n\n"
            f"<b>ID:</b> {html.escape(chat_id)}\n"
            f"<b>Name:</b> {html.escape(chat_data['title'])}\n"
        )

        if chat_data["private"]:
            msg += "<b>Type:</b> Private\n\n"
        else:
            msg += "<b>Type:</b> Group\n"
            if chat_data["accept_commands"]:
                msg += "<b>Accept-Commands:</b> All users\n\n"
            elif chat_data["allow_users"]:
                msg += "<b>Accept-Commands:</b> Allowed users\n\n"
            else:
                msg += "<b>Accept-comands:</b> None\n\n"

        msg += "<b>Allowed commands:</b>\n"
        if chat_data["accept_commands"]:
            enabled_commands = [key for key, enabled in chat_data["commands"].items() if enabled]
            if enabled_commands:
                escaped_commands = [html.escape(command) for command in enabled_commands]
                msg += ", ".join(escaped_commands) + "\n\n"
            else:
                msg += "You are NOT allowed to send any command.\n\n"
        elif chat_data["allow_users"]:
            msg += "Allowed users ONLY. See specific user settings for details.\n\n"
        else:
            msg += "You are NOT allowed to send any command.\n\n"

        msg += "<b>Get notification on:</b>\n"
        if chat_data["send_notifications"]:
            enabled_notifications = [key for key, enabled in chat_data["notifications"].items() if enabled]
            if enabled_notifications:
                escaped_notifications = [html.escape(notification) for notification in enabled_notifications]
                msg += ", ".join(escaped_notifications) + "\n\n"
            else:
                msg += "You will receive NO notifications.\n\n"
        else:
            msg += "You will receive NO notifications.\n\n"

        self.main.send_msg(msg, chatID=chat_id, markup="HTML")

    def cmdConnection(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            action, *args = parameter.split("|")
            actions = {
                "s": self.ConSettings,
                "c": self.ConConnect,
                "d": lambda cid, *_: self.ConDisconnect(cid),
            }
            if action in actions:
                actions[action](chat_id, args)
            return

        status, port, baudrate, profile = self.main._printer.get_current_connection()
        connection_options = octoprint.printer.get_connection_options()

        status_str = str(status)
        port_str = str(port)
        baud_str = "AUTO" if str(baudrate) == "0" else str(baudrate)
        profile_str = str(profile.get("name")) if profile is not None else "None"
        autoconnect_str = str(connection_options.get("autoconnect"))

        msg = (
            f"{get_emoji('info')} <b>Connection information</b>\n\n"
            f"<b>Status</b>: {html.escape(status_str)}\n\n"
            f"<b>Port</b>: {html.escape(port_str)}\n"
            f"<b>Baud</b>: {html.escape(baud_str)}\n"
            f"<b>Profile</b>: {html.escape(profile_str)}\n"
            f"<b>AutoConnect</b>: {html.escape(autoconnect_str)}\n\n"
        )

        msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""

        is_operational = self.main._printer.is_operational()
        is_busy = self.main._printer.is_printing() or self.main._printer.is_paused()

        btn_defaults = [f"{get_emoji('star')} Defaults", "/con_s"]
        btn_close = [f"{get_emoji('cancel')} Close", "no"]

        if is_operational:
            if is_busy:
                msg += f"{get_emoji('warning')} You can't disconnect while printing."

                command_buttons = [[btn_defaults, btn_close]]
            else:
                btn_disconnect = [f"{get_emoji('offline')} Disconnect", "/con_d"]
                command_buttons = [[btn_disconnect, btn_defaults, btn_close]]
        else:
            btn_connect = [f"{get_emoji('online')} Connect", "/con_c"]
            command_buttons = [[btn_connect, btn_defaults, btn_close]]

        self.main.send_msg(
            msg,
            responses=command_buttons,
            chatID=chat_id,
            markup="HTML",
            msg_id=msg_id,
        )

    def cmdTune(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            if params[0] == "feed":
                if len(params) > 1:
                    delta_str = params[1]

                    base = 2500 if delta_str.endswith("*") else 1000

                    if delta_str.startswith(("+", "-")):
                        sign = 1 if delta_str.startswith("+") else -1
                        magnitude = base / (10 ** len(delta_str))
                        self.temp_tune_rates["feedrate"] += sign * magnitude
                        self.temp_tune_rates["feedrate"] = max(50, min(self.temp_tune_rates["feedrate"], 200))
                    else:
                        self.main._printer.feed_rate(int(self.temp_tune_rates["feedrate"]))
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return

                msg = f"{get_emoji('feedrate')} Set feedrate.\nCurrent:  <b>{self.temp_tune_rates['feedrate']}%</b>"

                command_buttons = [
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
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            elif params[0] == "flow":
                if len(params) > 1:
                    delta_str = params[1]

                    base = 2500 if delta_str.endswith("*") else 1000

                    if delta_str.startswith(("+", "-")):
                        sign = 1 if delta_str.startswith("+") else -1
                        magnitude = base / (10 ** len(delta_str))
                        self.temp_tune_rates["flowrate"] += sign * magnitude
                        self.temp_tune_rates["flowrate"] = max(50, min(self.temp_tune_rates["flowrate"], 200))
                    else:
                        self.main._printer.flow_rate(int(self.temp_tune_rates["flowrate"]))
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return

                msg = f"{get_emoji('flowrate')} Set flowrate.\nCurrent: <b>{self.temp_tune_rates['flowrate']}%</b>"

                command_buttons = [
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
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            elif params[0] == "e":
                tool_number = int(params[1])
                tool_key = f"tool{tool_number}"

                temps = self.main._printer.get_current_temperatures()

                if len(params) <= 2:
                    self.temp_target_temps[tool_key] = temps[tool_key]["target"]
                else:
                    delta_str = params[2]

                    base = 5000 if delta_str.endswith("*") else 1000

                    if delta_str.startswith(("+", "-")):
                        sign = 1 if delta_str.startswith("+") else -1
                        magnitude = base / (10 ** len(delta_str))
                        self.temp_target_temps[tool_key] += sign * magnitude
                        self.temp_target_temps[tool_key] = max(self.temp_target_temps[tool_key], 0)

                    elif delta_str.startswith("s"):
                        self.main._printer.set_temperature(tool_key, self.temp_target_temps[tool_key])
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return

                    else:
                        self.main._printer.set_temperature(tool_key, 0)
                        self.temp_target_temps[tool_key] = 0
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return

                current_temp = temps[tool_key]["actual"]
                target_temp = self.temp_target_temps[tool_key]

                msg = (
                    f"{get_emoji('tool')} Set temperature for tool {tool_number}.\n"
                    f"Current: {current_temp:.02f}/<b>{target_temp}°C</b>"
                )

                command_buttons = [
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
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
            elif params[0] == "b":
                tool_key = "bed"

                temps = self.main._printer.get_current_temperatures()

                if len(params) <= 1:
                    self.temp_target_temps[tool_key] = temps[tool_key]["target"]
                else:
                    delta_str = params[1]

                    base = 5000 if delta_str.endswith("*") else 1000

                    if delta_str.startswith(("+", "-")):
                        sign = 1 if delta_str.startswith("+") else -1
                        magnitude = base / (10 ** len(delta_str))
                        self.temp_target_temps[tool_key] += sign * magnitude
                        self.temp_target_temps[tool_key] = max(self.temp_target_temps[tool_key], 0)

                    elif delta_str.startswith("s"):
                        self.main._printer.set_temperature(tool_key, self.temp_target_temps[tool_key])
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return

                    else:
                        self.main._printer.set_temperature(tool_key, 0)
                        self.temp_target_temps[tool_key] = 0
                        self.cmdTune(chat_id, from_id, cmd, "back", user)
                        return

                current_temp = temps[tool_key]["actual"]
                target_temp = self.temp_target_temps[tool_key]

                msg = (
                    f"{get_emoji('hotbed')} Set temperature for bed.\n"
                    f"Current: {current_temp:.02f}/<b>{target_temp}°C</b>"
                )

                command_buttons = [
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
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )
        else:
            msg = f"{get_emoji('settings')} <b>Tune print settings</b>"

            profile = self.main._printer_profile_manager.get_current()
            temps = self.main._printer.get_current_temperatures()

            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""

            command_buttons = [
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
                tool_command_buttons = []

                extruder = profile["extruder"]
                shared_nozzle = extruder.get("sharedNozzle", False)
                count = extruder.get("count", 1)

                if shared_nozzle:
                    tool_command_buttons.append([f"{get_emoji('tool')} Tool", "/tune_e_0"])
                else:
                    tool_command_buttons.extend(
                        [[f"{get_emoji('tool')} Tool {i}", f"/tune_e_{i}"] for i in range(count)]
                    )

                if profile["heatedBed"]:
                    tool_command_buttons.append([f"{get_emoji('hotbed')} Bed", "/tune_b"])

                if tool_command_buttons:
                    command_buttons.append(tool_command_buttons)

            command_buttons.append([[f"{get_emoji('cancel')} Close", "no"]])

            self.main.send_msg(msg, responses=command_buttons, chatID=chat_id, markup="HTML", msg_id=msg_id)

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
                                        "no",
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
                keys.append([[f"{get_emoji('cancel')} Close", "no"]])
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
                                        "no",
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
                keys.append([[f"{get_emoji('cancel')} Close", "no"]])
                msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
                self.main.send_msg(message, chatID=chat_id, responses=keys, msg_id=msg_id)
        else:
            message = (
                f"{get_emoji('warning')} No filament manager plugin installed. "
                "Please install <a href='https://plugins.octoprint.org/plugins/filamentmanager/'>FilamentManager</a> or "
                "<a href='https://plugins.octoprint.org/plugins/SpoolManager/'>SpoolManager</a>."
            )
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, markup="HTML", msg_id=msg_id)

    def cmdGCode(self, chat_id, from_id, cmd, parameter, user=""):
        if parameter and parameter != "back":
            params = parameter.split("_")
            self.main._printer.commands(params[0])
        else:
            message = f"{get_emoji('info')} call gCode commande with /gcode_XXX where XXX is the gcode command"
            msg_id = self.main.get_update_msg_id(chat_id) if parameter == "back" else ""
            self.main.send_msg(message, chatID=chat_id, msg_id=msg_id)

    def cmdHelp(self, chat_id, from_id, cmd, parameter, user=""):
        commands = [
            (cmd, info.get("desc", "No description provided"))
            for cmd, info in self.commandDict.items()
            if cmd.startswith("/")
        ]
        commands.sort()

        message = f"{get_emoji('info')} <b>The following commands are known:</b>\n\n"
        message += "\n".join(f"{html.escape(cmd)} - {html.escape(desc)}" for cmd, desc in commands)

        self.main.send_msg(
            message,
            chatID=chat_id,
            markup="HTML",
        )

    ############################################################################################
    # FILE HELPERS
    ############################################################################################

    def fileList(self, pathHash, page, cmd, chat_id, wait=0):
        try:
            full_path = self.dirHashDict[pathHash]
            path_parts = full_path.split("/")
            destination_root = path_parts[0]
            relative_path = "/".join(path_parts[1:])
            path_without_root = relative_path if len(path_parts) > 1 else full_path

            file_listing = self.main._file_manager.list_files(path=relative_path, recursive=False)
            files_in_destination = file_listing.get(destination_root, {})

            # --- Get folders ---
            folders = {name: data for name, data in files_in_destination.items() if data.get("type") == "folder"}
            folder_buttons = []
            for folder_name in sorted(folders):
                folder_hash = self.hashMe(full_path + folder_name + "/", 8)
                folder_buttons.append(
                    [
                        f"{get_emoji('folder')} {folder_name}",
                        f"{cmd}_{pathHash}|0|{folder_hash}|dir",
                    ]
                )

            # --- Get files ---
            files = {name: data for name, data in files_in_destination.items() if data.get("type") == "machinecode"}
            file_buttons = []
            for filename, file_data in sorted(files.items(), key=lambda x: x[1].get("date", 0), reverse=True):
                file_base_name = ".".join(filename.split(".")[:-1])
                try:
                    if "history" in file_data:
                        history_list = file_data["history"]
                        history_list.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                        latest_history = history_list[0] if history_list else None
                        if latest_history and latest_history.get("success"):
                            display_filename = f"{get_emoji('hooray')} {file_base_name}"
                        elif latest_history:
                            display_filename = f"{get_emoji('warning')} {file_base_name}"
                        else:
                            display_filename = f"{get_emoji('file')} {file_base_name}"
                    else:
                        display_filename = f"{get_emoji('new')} {file_base_name}"
                except Exception:
                    self._logger.exception(f"Error processing history for file '{filename}'")
                    display_filename = f"{get_emoji('file')} {file_base_name}"

                file_hash = self.hashMe(path_without_root + filename)
                if file_hash:
                    command = f"{cmd}_{pathHash}|{page}|{file_hash}"
                    file_buttons.append([display_filename, command])

            # --- Combine folders and files and sort them ---
            folder_buttons_sorted = sorted(folder_buttons)
            if not self.main._settings.get_boolean(["fileOrder"]):
                folder_and_file_buttons = folder_buttons_sorted + sorted(file_buttons)
            else:
                folder_and_file_buttons = folder_buttons_sorted + file_buttons

            # --- Pagination ---
            page_size = 10
            total_pages = (len(folder_and_file_buttons) + page_size - 1) // page_size
            previous_page = max(0, page - 1)
            next_page = min(total_pages - 1, page + 1)
            paginated_folder_and_file_buttons = folder_and_file_buttons[page * page_size : (page + 1) * page_size]

            # --- Create command buttons ---
            command_buttons = []

            # Folder and file buttons
            folder_and_file_buttons_row = []
            for i, button in enumerate(paginated_folder_and_file_buttons, start=1):
                folder_and_file_buttons_row.append(button)
                if i % 2 == 0:  # 2 file buttons per row
                    command_buttons.append(folder_and_file_buttons_row)
                    folder_and_file_buttons_row = []
            if folder_and_file_buttons_row:
                command_buttons.append(folder_and_file_buttons_row)

            # Last row: back, prev/next page, settings, close
            nav_and_actions_row = []

            # Back button (only within subfolders)
            is_root_folder = len(path_parts) < 3
            if not is_root_folder:
                back_path = "/".join(full_path.split("/")[:-2]) + "/"
                nav_and_actions_row.append(
                    [
                        f"{get_emoji('back')} Back",
                        f"{cmd}_{self.hashMe(back_path, 8)}|0",
                    ]
                )

            # Prev/next page
            if previous_page != next_page:
                if previous_page != page:
                    nav_and_actions_row.append([f"{get_emoji('up')} Prev page", f"{cmd}_{pathHash}|{previous_page}"])
                if next_page != page:
                    nav_and_actions_row.append([f"{get_emoji('down')} Next page", f"{cmd}_{pathHash}|{next_page}"])

            # Settings and close
            nav_and_actions_row.extend(
                [
                    [
                        f"{get_emoji('settings')} Settings",
                        f"{cmd}_{pathHash}|{page}|0|s",
                    ],
                    [
                        f"{get_emoji('cancel')} Close",
                        "no",
                    ],
                ]
            )

            command_buttons.append(nav_and_actions_row)

            # --- Create message ---
            page_str = f"{page + 1} / {total_pages}"
            msg = f"{get_emoji('save')} Files in <code>/{html.escape(path_without_root[:-1])}</code>    [{page_str}]"

            # --- Send message ---
            self.main.send_msg(
                msg,
                chatID=chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=self.main.get_update_msg_id(chat_id),
                delay=wait,
            )
        except Exception:
            self._logger.exception("Caught an exception in fileList")

    def fileDetails(self, pathHash, page, cmd, fileHash, chat_id, from_id, wait=0):
        # Lookup file data and metadata
        dest, path, file = self.find_file_by_hash(fileHash)
        self.tmpFileHash = ""
        meta = self.main._file_manager.get_metadata(dest, path)
        analysis = meta.get("analysis", {})

        # Message header
        msg = f"{get_emoji('info')} <b>File information</b>\n\n"
        msg += f"{get_emoji('name')} <b>Name:</b> {html.escape(path)}"

        # Upload timestamp
        try:
            dt = datetime.datetime.fromtimestamp(file["date"])
            msg += f"\n{get_emoji('calendar')} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            self._logger.exception("Caught an exception getting file date")

        # Print history
        history = file.get("history", [])
        if not history:
            msg += f"\n{get_emoji('new')} <b>Number of Print:</b> 0"
        else:
            try:
                history.sort(key=lambda x: x["timestamp"], reverse=True)
                success = history[0].get("success", False)
                icon = get_emoji("hooray") if success else get_emoji("warning")
            except Exception:
                self._logger.exception("Caught an exception reading history list")
                icon = get_emoji("file")
            msg += f"\n{icon} <b>Number of Print:</b> {len(history)}"

        # File size
        msg += f"\n{get_emoji('filesize')} <b>Size:</b> {self.formatSize(file['size'])}"

        # Filament info
        filament_length = 0
        filament = analysis.get("filament", {})
        if filament:
            msg += f"\n{get_emoji('filament')} <b>Filament:</b> "
            if len(filament) == 1 and "length" in filament.get("tool0", {}):
                msg += self.formatFilament(filament["tool0"])
                filament_length += float(filament["tool0"]["length"])
            else:
                for tool in sorted(filament):
                    length = filament[tool].get("length")
                    if length is not None:
                        msg += f"\n      {html.escape(tool)}: {self.formatFilament(filament[tool])}"
                        filament_length += float(length)

        # Print time
        print_time = analysis.get("estimatedPrintTime")
        if print_time:
            msg += f"\n{get_emoji('stopwatch')} <b>Print Time:</b> {self.formatFuzzyPrintTime(print_time)}"

            # ETA
            try:
                time_finish = self.main.calculate_ETA(print_time)
                msg += f"\n{get_emoji('finish')} <b>Completed Time:</b> {html.escape(time_finish)}"
            except Exception:
                self._logger.exception("Caught an exception calculating ETA")

            # Cost calculation (if plugin active)
            if self.main._plugin_manager.get_plugin("cost", True) and filament_length:
                try:
                    cp_h = self.main._settings.global_get_float(["plugins", "cost", "cost_per_time"])
                    cp_m = self.main._settings.global_get_float(["plugins", "cost", "cost_per_length"])
                    curr = self.main._settings.global_get(["plugins", "cost", "currency"])
                    cost = filament_length / 1000 * cp_m + print_time / 3600 * cp_h
                    msg += f"\n{get_emoji('cost')} <b>Cost:</b> {html.escape(curr)}{cost:.02f}"
                except Exception:
                    self._logger.exception("Caught an exception calculating cost")

        # Upload the thumbnail image to imgbb to get a public URL
        try:
            api_key = self.main._settings.get(["imgbbApiKey"])
            self._logger.info(f"Get thumbnail url for path={path}")

            meta = self.main._file_manager.get_metadata(octoprint.filemanager.FileDestinations.LOCAL, path)
            thumbnail_path = meta.get("thumbnail")

            if api_key and thumbnail_path:
                thumbnail_url = f"http://localhost:{self.port}/{thumbnail_path}"
                thumbnail_response = requests.get(thumbnail_url)

                if thumbnail_response.ok:
                    encoded_img = base64.b64encode(thumbnail_response.content)
                    upload_url = "https://api.imgbb.com/1/upload"
                    payload = {"key": api_key, "image": encoded_img}

                    res = requests.post(upload_url, payload)
                    if res.ok:
                        image_url = res.json()["data"]["url"]
                        msg = f"<a href='{image_url}'>&#8199;</a>\n{msg}"
        except Exception:
            self._logger.exception("Caught an exception uploading thumbnail to imgbb")

        # Create command buttons
        command_buttons = []

        # First row: Print (if allowed) + Details
        first_row = []
        if self.main.is_command_allowed(chat_id, from_id, "/print"):
            first_row.append([f"{get_emoji('play')} Print", f"/print_{fileHash}"])
        first_row.append([f"{get_emoji('search')} Details", f"{cmd}_{pathHash}|{page}|{fileHash}|inf"])
        command_buttons.append(first_row)

        # Second row: File ops if allowed
        if self.main.is_command_allowed(chat_id, from_id, "/files"):
            second_row = [
                [f"{get_emoji('cut')} Move", f"{cmd}_{pathHash}|{page}|{fileHash}|m"],
                [f"{get_emoji('copy')} Copy", f"{cmd}_{pathHash}|{page}|{fileHash}|c"],
                [f"{get_emoji('delete')} Delete", f"{cmd}_{pathHash}|{page}|{fileHash}|d"],
            ]
            command_buttons.append(second_row)

            # Third row: Download + Back
            third_row = []
            if self.dirHashDict[pathHash].split("/")[0] == octoprint.filemanager.FileDestinations.LOCAL:
                third_row.append([f"{get_emoji('download')} Download", f"{cmd}_{pathHash}|{page}|{fileHash}|dl"])
            third_row.append([f"{get_emoji('back')} Back", f"{cmd}_{pathHash}|{page}"])
            command_buttons.append(third_row)
        else:
            # If file commands not allowed, just add Back alone
            command_buttons.append([[f"{get_emoji('back')} Back", f"{cmd}_{pathHash}|{page}"]])

        # Send the message
        self.main.send_msg(
            msg,
            chatID=chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=self.main.get_update_msg_id(chat_id),
            delay=wait,
        )

    def fileOption(self, loc, page, cmd, hash, opt, chat_id, from_id):
        if opt != "m_m" and opt != "c_c" and not opt.startswith("s"):
            # Lookup file data and metadata
            dest, path, file = self.find_file_by_hash(hash)
            meta = self.main._file_manager.get_metadata(dest, path)

        if opt.startswith("inf"):
            # Lookup additional file data
            analysis = meta.get("analysis", {})
            statistics = meta.get("statistics", {})
            history = meta.get("history", {})

            # Message header
            msg = f"{get_emoji('info')} <b>File information</b>\n\n"
            msg += f"{get_emoji('name')} <b>Name:</b> {html.escape(path)}"

            # Upload timestamp
            try:
                dt = datetime.datetime.fromtimestamp(file["date"])
                msg += f"\n{get_emoji('calendar')} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}"
            except Exception:
                self._logger.exception("Caught an exception getting file date")

            # File size
            msg += f"\n {get_emoji('filesize')} <b>Size:</b> {self.formatSize(file['size'])}"

            # Filament info
            filament_length = 0
            filament = analysis.get("filament", {})
            if filament:
                msg += f"\n{get_emoji('filament')} <b>Filament:</b> "
                if len(filament) == 1 and "length" in filament.get("tool0", {}):
                    msg += self.formatFilament(filament["tool0"])
                    filament_length += float(filament["tool0"]["length"])
                else:
                    for tool in sorted(filament):
                        length = filament[tool].get("length")
                        if length is not None:
                            msg += f"\n      {html.escape(tool)}: {self.formatFilament(filament[tool])}"
                            filament_length += float(length)

            # Print time
            print_time = analysis.get("estimatedPrintTime")
            if print_time:
                msg += f"\n{get_emoji('stopwatch')} <b>Print Time:</b> {self.formatFuzzyPrintTime(print_time)}"

                # ETA
                try:
                    time_finish = self.main.calculate_ETA(print_time)
                    msg += f"\n{get_emoji('finish')} <b>Completed Time:</b> {html.escape(time_finish)}"
                except Exception:
                    self._logger.exception("Caught an exception calculating ETA")

                # Cost calculation (if plugin active)
                if self.main._plugin_manager.get_plugin("cost", True) and filament_length:
                    try:
                        cp_h = self.main._settings.global_get_float(["plugins", "cost", "cost_per_time"])
                        cp_m = self.main._settings.global_get_float(["plugins", "cost", "cost_per_length"])
                        curr = self.main._settings.global_get(["plugins", "cost", "currency"])
                        cost = filament_length / 1000 * cp_m + print_time / 3600 * cp_h
                        msg += f"\n{get_emoji('cost')} <b>Cost:</b> {html.escape(curr)}{cost:.02f}"
                    except Exception:
                        self._logger.exception("Caught an exception calculating cost")

            # Average print times
            try:
                average_print_times = statistics.get("averagePrintTime")
                if average_print_times:
                    msg += "\n\n<b>Average Print Time:</b>"
                    for profile_id, average_print_time in islice(average_print_times.items(), 5):
                        try:
                            profile = self.main._printer_profile_manager.get(profile_id)
                            msg += f"\n      {html.escape(profile['name'])}: {self.formatDuration(average_print_time)}"
                        except Exception:
                            self._logger.exception(f"Error processing average print time for profile '{profile_id}'")
            except Exception:
                self._logger.exception("Caught an exception retrieving average print times")

            # Last print times
            last_print_times = statistics.get("lastPrintTime")
            if last_print_times:
                msg += "\n\n<b>Last Print Time:</b>"
                for profile_id, last_print_time in islice(last_print_times.items(), 5):
                    try:
                        profile = self.main._printer_profile_manager.get(profile_id)
                        msg += f"\n      {html.escape(profile['name'])}: {self.formatDuration(last_print_time)}"
                    except Exception:
                        self._logger.exception(
                            f"Caught an exception processing last print time for profile '{profile_id}'"
                        )

            # Prints history
            if history:
                msg += "\n\n<b>Print History:</b>"
                for history_entry in islice(history, 5):
                    try:
                        timestamp = history_entry.get("timestamp")
                        if timestamp:
                            formatted_ts = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                            msg += f"\n      Timestamp: {formatted_ts}"

                        print_time = history_entry.get("printTime")
                        if print_time is not None:
                            msg += f"\n      Print Time: {self.formatDuration(print_time)}"

                        profile_id = history_entry.get("printerProfile")
                        if profile_id:
                            try:
                                profile = self.main._printer_profile_manager.get(profile_id)
                                msg += f"\n      Printer Profile: {html.escape(profile['name'])}"
                            except Exception:
                                self._logger.exception(f"Failed to get printer profile '{profile_id}'")

                        success = history_entry.get("success")
                        if success is not None:
                            msg += "\n      Successfully printed" if success else "\n      Print failed"

                        msg += "\n"
                    except Exception:
                        self._logger.exception("Caught an exception processing history")

            # Upload the thumbnail image to imgbb to get a public URL
            try:
                api_key = self.main._settings.get(["imgbbApiKey"])
                self._logger.info(f"Get thumbnail url for path={path}")

                meta = self.main._file_manager.get_metadata(octoprint.filemanager.FileDestinations.LOCAL, path)
                thumbnail_path = meta.get("thumbnail")

                if api_key and thumbnail_path:
                    thumbnail_url = f"http://localhost:{self.port}/{thumbnail_path}"
                    thumbnail_response = requests.get(thumbnail_url)

                    if thumbnail_response.ok:
                        encoded_img = base64.b64encode(thumbnail_response.content)
                        upload_url = "https://api.imgbb.com/1/upload"
                        payload = {"key": api_key, "image": encoded_img}

                        res = requests.post(upload_url, payload)
                        if res.ok:
                            image_url = res.json()["data"]["url"]
                            msg = f"<a href='{image_url}'>&#8199;</a>\n{msg}"
            except Exception:
                self._logger.exception("Caught an exception uploading thumbnail to imgbb")

            # Create command buttons
            command_buttons = [
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"{cmd}_{loc}|{page}|{hash}",
                    ]
                ]
            ]

            # Send the message
            self.main.send_msg(
                msg,
                chatID=chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

        elif opt.startswith("dl"):
            try:
                self.main.send_file(chat_id, self.main._file_manager.path_on_disk(dest, path))
            except Exception:
                self._logger.exception(f"Caught an exception sending file {path} to {chat_id}")
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
                    msg = f"{get_emoji('info')} File {pathM} moved"
                    self.main.send_msg(
                        msg,
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileList(loc, page, cmd, chat_id, wait=3)
                else:
                    msg = (f"{get_emoji('warning')} FAILED: Move file {pathM}\nReason: {cpRes}",)
                    self.main.send_msg(
                        msg,
                        chatID=chat_id,
                        msg_id=msg_id,
                    )
                    self.fileDetails(loc, page, cmd, self.tmpFileHash, chat_id, from_id, wait=3)
            else:
                msg = (f"{get_emoji('question')} <b>Choose destination to move file</b>",)

                self.tmpFileHash = hash

                command_buttons = [
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{cmd}_{loc}|{page}|{hash}",
                        ]
                    ]
                ]
                for key, val in sorted(list(self.dirHashDict.items()), key=operator.itemgetter(1)):
                    command_buttons.append(
                        [
                            [
                                f"{get_emoji('folder')} {self.dirHashDict[key]}",
                                f"{cmd}_{loc}|{page}|{key}|m_m",
                            ]
                        ]
                    )

                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=msg_id,
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
                msg = f"{get_emoji('question')} <b>Choose destination to copy file</b>"

                self.tmpFileHash = hash

                command_buttons = [
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{cmd}_{loc}|{page}|{hash}",
                        ]
                    ]
                ]
                for key, val in sorted(list(self.dirHashDict.items()), key=operator.itemgetter(1)):
                    command_buttons.append(
                        [
                            [
                                f"{get_emoji('folder')} {self.dirHashDict[key]}",
                                f"{cmd}_{loc}|{page}|{key}|c_c",
                            ]
                        ]
                    )

                self.main.send_msg(
                    msg,
                    chatID=chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=msg_id,
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
                command_buttons = [
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
                    responses=command_buttons,
                    msg_id=msg_id,
                )
        elif opt.startswith("s"):
            if opt == "s_n":
                self.main._settings.set_boolean(["fileOrder"], False)
                self.main._settings.save()
                self.fileList(loc, page, cmd, chat_id)
            elif opt == "s_d":
                self.main._settings.set_boolean(["fileOrder"], True)
                self.main._settings.save()
                self.fileList(loc, page, cmd, chat_id)
            else:
                msg = f"{get_emoji('question')} <b>Choose sorting order of files</b>"

                command_buttons = [
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
                    msg,
                    chatID=chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=self.main.get_update_msg_id(chat_id),
                )

    ### From filemanager plugin - https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
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
            connection_options = octoprint.printer.get_connection_options()
            profile = self.main._printer_profile_manager.get_default()

            port_str = str(connection_options.get("portPreference"))
            baud_str = str(connection_options.get("baudratePreference") or "AUTO")
            profile_name_str = str(profile.get("name"))
            autoconnect_str = str(connection_options.get("autoconnect"))

            msg = (
                f"{get_emoji('settings')} Default connection settings\n"
                f"\n<b>Port:</b> {html.escape(port_str)}"
                f"\n<b>Baud:</b> {html.escape(baud_str)}"
                f"\n<b>Profile:</b> {html.escape(profile_name_str)}"
                f"\n<b>AutoConnect:</b> {html.escape(autoconnect_str)}"
            )

            command_buttons = [
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
            ]

            self.main.send_msg(
                msg,
                chatID=chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=self.main.get_update_msg_id(chat_id),
            )

    def ConPort(self, chat_id, parameter, parent):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set(["serial", "port"], parameter[0])
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

    def ConBaud(self, chat_id, parameter, parent):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set_int(["serial", "baudrate"], parameter[0])
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

    def ConProfile(self, chat_id, parameter, parent):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set(["printerProfiles", "default"], parameter[0])
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

    def ConAuto(self, chat_id, parameter):
        if parameter:
            self._logger.debug(f"SETTING: {parameter[0]}")
            self.main._settings.global_set_boolean(["serial", "autoconnect"], parameter[0])
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

    def ConConnect(self, chat_id, parameter):
        if parameter:
            if parameter[0] == "a":
                self.temp_connection_settings.extend([None, None, None])
            elif parameter[0] == "d":
                self.temp_connection_settings.extend(
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
                self.temp_connection_settings.append(parameter[1])
                self.ConBaud(chat_id, [], "c")
                return
            elif parameter[0] == "b":
                self.temp_connection_settings.append(parameter[1])
                self.ConProfile(chat_id, [], "c")
                return
            elif parameter[0] == "pr":
                self.temp_connection_settings.append(parameter[1])
            self.main.send_msg(
                f"{get_emoji('info')} Connecting...",
                chatID=chat_id,
                msg_id=self.main.get_update_msg_id(chat_id),
            )
            self.main._printer.connect(
                port=self.temp_connection_settings[0],
                baudrate=self.temp_connection_settings[1],
                profile=self.temp_connection_settings[2],
            )
            self.temp_connection_settings = []
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

    def formatFilament(self, filament):
        # from octoprint/static/js/app/helpers.js transferred to python
        if not filament or "length" not in filament:
            return "-"
        result = f"{float(filament['length']) / 1000:.02f} m"
        if "volume" in filament and filament["volume"]:
            result += f" / {float(filament['volume']):.02f} cm^3"
        return result

    def formatDuration(self, seconds):
        if seconds is None:
            return "-"
        if seconds < 1:
            return "00:00:00"
        s = int(seconds) % 60
        m = (int(seconds) % 3600) / 60
        h = int(seconds) / 3600
        return "%02d:%02d:%02d" % (h, m, s)

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
