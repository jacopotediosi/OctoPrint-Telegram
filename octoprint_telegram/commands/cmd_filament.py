import requests

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdFilament(BaseCommand):
    _spoolManagerPluginImplementation = None

    def execute(self, context: CommandContext):
        if self.main._plugin_manager.get_plugin("filamentmanager", True):
            if context.parameter and context.parameter != "back":
                self._logger.info(f"Parameter received for filament: {context.parameter}")
                params = context.parameter.split("_")
                apikey = self.main._settings.global_get(["api", "key"])
                errorText = ""
                if params[0] == "spools":
                    try:
                        resp = requests.get(
                            f"http://localhost:{self.main.port}/plugin/filamentmanager/spools?apikey={apikey}"
                        )
                        resp2 = requests.get(
                            f"http://localhost:{self.main.port}/plugin/filamentmanager/selections?apikey={apikey}"
                        )
                        if resp.status_code != 200:
                            errorText = resp.text
                        resp = resp.json()
                        resp2 = resp2.json()
                        self._logger.info(f"Spools: {resp['spools']}")
                        msg = f"{get_emoji('info')} Available filament spools are:\n"
                        for spool in resp["spools"]:
                            weight = spool["weight"]
                            used = spool["used"]
                            percent = int(100 - (used / weight * 100))
                            msg += f"{spool['profile']['vendor']} {spool['name']} {spool['profile']['material']} [{percent}%]\n"
                        for selection in resp2["selections"]:
                            if selection["tool"] == 0:
                                msg += (
                                    f"\n\nCurrently selected: "
                                    f"{selection['spool']['profile']['vendor']} "
                                    f"{selection['spool']['name']} "
                                    f"{selection['spool']['profile']['material']}"
                                )
                        self.main.send_msg(
                            msg,
                            chatID=context.chat_id,
                            msg_id=context.msg_id_to_update,
                        )
                    except ValueError:
                        msg = f"{get_emoji('attention')} Error getting spools. Are you sure, you have installed the Filament Manager Plugin?"
                        if errorText != "":
                            msg += f"\nError text: {errorText}"
                        self.main.send_msg(
                            msg,
                            chatID=context.chat_id,
                            msg_id=context.msg_id_to_update,
                        )
                if params[0] == "changeSpool":
                    self._logger.info(f"Command to change spool: {params}")
                    if len(params) > 1:
                        self._logger.info(f"Changing to spool: {params[1]}")
                        try:
                            payload = {"selection": {"spool": {"id": params[1]}, "tool": 0}}
                            self._logger.info(f"Payload: {payload}")
                            resp = requests.patch(
                                f"http://localhost:{self.main.port}/plugin/filamentmanager/selections/0?apikey={apikey}",
                                json=payload,
                                headers={"Content-Type": "application/json"},
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            self._logger.info(f"Response: {resp}")
                            resp = resp.json()
                            msg = (
                                f"{get_emoji('check')} Selected spool is now: "
                                f"{resp['selection']['spool']['profile']['vendor']} "
                                f"{resp['selection']['spool']['name']} "
                                f"{resp['selection']['spool']['profile']['material']}"
                            )
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                msg_id=context.msg_id_to_update,
                            )
                        except ValueError:
                            msg = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                msg += f"\nError text: {errorText}"
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                msg_id=context.msg_id_to_update,
                            )
                    else:
                        self._logger.info("Asking for spool")
                        try:
                            resp = requests.get(
                                f"http://localhost:{self.main.port}/plugin/filamentmanager/spools?apikey={apikey}"
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            resp = resp.json()
                            msg = f"{get_emoji('question')} which filament spool do you want to select?"
                            command_buttons = []
                            tmpKeys = []
                            i = 1
                            for spool in resp["spools"]:
                                self._logger.info(f"Appending spool: {spool}")
                                tmpKeys.append(
                                    [
                                        f"{spool['profile']['vendor']} {spool['name']} {spool['profile']['material']}",
                                        f"{context.cmd}_changeSpool_{spool['id']}",
                                    ]
                                )
                                if i % 2 == 0:
                                    command_buttons.append(tmpKeys)
                                    tmpKeys = []
                                i += 1
                            if len(tmpKeys) > 0:
                                command_buttons.append(tmpKeys)
                            command_buttons.append(
                                [
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "close",
                                    ]
                                ]
                            )
                            self._logger.info("Sending message")
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                responses=command_buttons,
                                msg_id=context.msg_id_to_update,
                            )
                        except ValueError:
                            msg = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                msg += f"\nError text: {errorText}"
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                msg_id=context.msg_id_to_update,
                            )
            else:
                msg = f"{get_emoji('info')} The following Filament Manager commands are known."
                command_buttons = []
                command_buttons.append([["Show spools", f"{context.cmd}_spools"]])
                command_buttons.append([["Change spool", f"{context.cmd}_changeSpool"]])
                command_buttons.append([[f"{get_emoji('cancel')} Close", "close"]])
                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
        elif self.main._plugin_manager.get_plugin("SpoolManager", True):
            if context.parameter and context.parameter != "back":
                self._logger.info(f"Parameter received for filament: {context.parameter}")
                params = context.parameter.split("_")
                apikey = self.main._settings.global_get(["api", "key"])
                errorText = ""
                if params[0] == "spools":
                    try:
                        if self._spoolManagerPluginImplementation is None:
                            self._spoolManagerPluginImplementation = self.main._plugin_manager.get_plugin(
                                "SpoolManager", True
                            )
                        msg = f"SpoolManager: {self._spoolManagerPluginImplementation.SpoolManagerAPI.load_allSpools()}"
                        # selectedSpool = self._spoolManagerPluginImplementation.filamentManager.loadSelectedSpool()
                        # allSpool = self._spoolManagerPluginImplementation.filamentManager.load_allSpools
                        # message = f"selectedSpool={selectedSpool}\nallSpool={allSpool}"

                        # resp = requests.get(f"http://localhost:{self.main.port}/plugin/spoolmanager/loadSpoolsByQuery?={query}")
                        # resp2 = requests.get(f"http://localhost:{self.main.port}/plugin/filamentmanager/selections?apikey={apikey}")
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
                        self.main.send_msg(
                            msg,
                            chatID=context.chat_id,
                            msg_id=context.msg_id_to_update,
                        )
                    except ValueError:
                        msg = f"{get_emoji('attention')} Error getting spools. Are you sure you have installed the Spool Manager Plugin?"
                        if errorText != "":
                            msg += f"\nError text: {errorText}"
                        self.main.send_msg(
                            msg,
                            chatID=context.chat_id,
                            msg_id=context.msg_id_to_update,
                        )
                if params[0] == "changeSpool":
                    self._logger.info(f"Command to change spool: {params}")
                    if len(params) > 1:
                        self._logger.info(f"Changing to spool: {params[1]}")
                        try:
                            payload = {"selection": {"spool": {"id": params[1]}, "tool": 0}}
                            self._logger.info(f"Payload: {payload}")
                            resp = requests.patch(
                                f"http://localhost:{self.main.port}/plugin/filamentmanager/selections/0?apikey={apikey}",
                                json=payload,
                                headers={"Content-Type": "application/json"},
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            self._logger.info(f"Response: {resp}")
                            resp = resp.json()
                            msg = (
                                f"{get_emoji('check')} Selected spool is now: "
                                f"{resp['selection']['spool']['profile']['vendor']} "
                                f"{resp['selection']['spool']['name']} "
                                f"{resp['selection']['spool']['profile']['material']}"
                            )
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                msg_id=context.msg_id_to_update,
                            )
                        except ValueError:
                            msg = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                msg += f"\nError text: {errorText}"
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                msg_id=context.msg_id_to_update,
                            )
                    else:
                        self._logger.info("Asking for spool")
                        try:
                            resp = requests.get(
                                f"http://localhost:{self.main.port}/plugin/filamentmanager/spools?apikey={apikey}"
                            )
                            if resp.status_code != 200:
                                errorText = resp.text
                            resp = resp.json()
                            msg = f"{get_emoji('question')} which filament spool do you want to select?"
                            command_buttons = []
                            tmpKeys = []
                            i = 1
                            for spool in resp["spools"]:
                                self._logger.info(f"Appending spool: {spool}")
                                tmpKeys.append(
                                    [
                                        f"{spool['profile']['vendor']} {spool['name']} {spool['profile']['material']}",
                                        f"{context.cmd}_changeSpool_{spool['id']}",
                                    ]
                                )
                                if i % 2 == 0:
                                    command_buttons.append(tmpKeys)
                                    tmpKeys = []
                                i += 1
                            if len(tmpKeys) > 0:
                                command_buttons.append(tmpKeys)
                            command_buttons.append(
                                [
                                    [
                                        f"{get_emoji('cancel')} Close",
                                        "close",
                                    ]
                                ]
                            )
                            self._logger.info("Sending message")
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                responses=command_buttons,
                                msg_id=context.msg_id_to_update,
                            )
                        except ValueError:
                            msg = f"{get_emoji('attention')} Error changing spool"
                            if errorText != "":
                                msg += f"\nError text: {errorText}"
                            self.main.send_msg(
                                msg,
                                chatID=context.chat_id,
                                msg_id=context.msg_id_to_update,
                            )
            else:
                msg = f"{get_emoji('info')} The following Filament Manager commands are known."

                command_buttons = [
                    [["Show spools", f"{context.cmd}_spools"]],
                    [["Change spool", f"{context.cmd}_changeSpool"]],
                    [[f"{get_emoji('cancel')} Close", "close"]],
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
        else:
            msg = (
                f"{get_emoji('warning')} No filament manager plugin installed. "
                "Please install <a href='https://plugins.octoprint.org/plugins/filamentmanager/'>FilamentManager</a> or "
                "<a href='https://plugins.octoprint.org/plugins/SpoolManager/'>SpoolManager</a>."
            )

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )
