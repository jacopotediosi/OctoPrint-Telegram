import html
from abc import ABC, abstractmethod

import requests

from ..emoji import Emoji
from ..utils import StringUtils
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdPower(BaseCommand):
    def execute(self, context: CommandContext):
        supported_plugins = [
            self.DomoticzPowerPlugin(self),
            self.EnclosurePowerPlugin(self),
            self.GpioControlPowerPlugin(self),
            self.IkeaTradfriPowerPlugin(self),
            self.MyStromSwitchPowerPlugin(self),
            self.OctoHuePowerPlugin(self),
            self.OctoLightPowerPlugin(self),
            self.OctoLightHAPowerPlugin(self),
            self.OctoRelayPowerPlugin(self),
            self.OrviboS20PowerPlugin(self),
            self.PSUControlPowerPlugin(self),
            self.TasmotaPowerPlugin(self),
            self.TasmotaMQTTPowerPlugin(self),
            self.TPLinkSmartplugPowerPlugin(self),
            self.TuyaSmartplugPowerPlugin(self),
            self.USBRelayControlPowerPlugin(self),
            self.WemoSwitchPowerPlugin(self),
            self.WledPowerPlugin(self),
            self.WS281xPowerPlugin(self),
            self.WyzePowerPlugin(self),
        ]

        available_plugins = [
            plugin_instance
            for plugin_instance in supported_plugins
            if self.main._plugin_manager.get_plugin(plugin_instance.plugin_id, True)
        ]

        if not available_plugins:
            message = render_emojis(
                "{emo:warning} No power manager plugin installed. Please install one of the following plugins:\n"
            )
            for plugin_handler in supported_plugins:
                message += f"- <a href='https://plugins.octoprint.org/plugins/{html.escape(plugin_handler.plugin_id)}/'>{html.escape(plugin_handler.plugin_name)}</a>\n"

            self.main.send_msg(
                message,
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )

            return

        if not context.parameter:  # Command was /power, show plugs list
            message = render_emojis("{emo:question} Which plug do you want to manage?")

            plug_buttons = []
            for plugin_handler in available_plugins:
                try:
                    for plug_data in plugin_handler.get_plugs_data():
                        label = plug_data["label"]

                        is_on = plug_data["is_on"]
                        status_emoji_name = "online" if is_on else "offline"

                        data = plug_data["data"]
                        command = (
                            context.cmd
                            + "_"
                            + plugin_handler.plugin_id.replace("_", "\\_")
                            + "_"
                            + str(data).replace("_", "\\_")
                        )

                        plug_buttons.append([render_emojis(f"{{emo:{status_emoji_name}}} {label}"), command])
                except Exception:
                    self._logger.exception("Caught an exception getting %s plugs", plugin_handler.plugin_id)

            max_per_row = 3
            plug_button_rows = [plug_buttons[i : i + max_per_row] for i in range(0, len(plug_buttons), max_per_row)]
            command_buttons = plug_button_rows + [[[render_emojis("{emo:cancel} Close"), "close"]]]

            self.main.send_msg(
                message,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

        else:
            splitted_parameters = StringUtils.split_with_escape_handling(context.parameter, "_")
            plugin_id, plug_data, action = (splitted_parameters + [None] * 3)[:3]

            plugin_handler = next((plugin for plugin in available_plugins if plugin.plugin_id == plugin_id), None)

            if plugin_handler is None:
                message = render_emojis(
                    f"{{emo:attention}} Plugin <code>{html.escape(plugin_id)}</code> is not available!"
                )
                command_buttons = [
                    [[render_emojis("{emo:back} Back"), context.cmd], [render_emojis("{emo:cancel} Close"), "close"]]
                ]
                self.main.send_msg(
                    message,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
                return

            if action is None:  # Command was /power_plugin\_id_plug\_data, show plug status and ask for action
                plugs = plugin_handler.get_plugs_data()
                selected_plug = next((plug for plug in plugs if str(plug["data"]) == plug_data), None)

                if selected_plug is None:
                    message = render_emojis("{emo:attention} Selected plug not found!")
                    command_buttons = [
                        [
                            [render_emojis("{emo:back} Back"), context.cmd],
                            [render_emojis("{emo:cancel} Close"), "close"],
                        ]
                    ]
                    self.main.send_msg(
                        message,
                        chatID=context.chat_id,
                        markup="HTML",
                        responses=command_buttons,
                        msg_id=context.msg_id_to_update,
                    )
                    return

                label = selected_plug["label"]
                is_on = selected_plug["is_on"]
                status_text = "ON" if is_on else "OFF"
                status_emoji_name = "online" if is_on else "offline"

                message = render_emojis(
                    f"{{emo:info}} Plug <code>{html.escape(label)}</code> is {{emo:{status_emoji_name}}} {status_text}.\n"
                    "{emo:question} What do you want to do?"
                )

                original_command = f"{context.cmd}_{context.parameter}"
                command_buttons = [
                    [
                        [render_emojis("{emo:online} Turn ON"), f"{original_command}_on"],
                        [render_emojis("{emo:offline} Turn OFF"), f"{original_command}_off"],
                    ],
                    [[render_emojis("{emo:back} Back"), context.cmd], [render_emojis("{emo:cancel} Close"), "close"]],
                ]

                self.main.send_msg(
                    message,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
            else:  # Command was /power_plugin\_id_plug\_data_action, execute action
                action_methods = {"on": plugin_handler.turn_on, "off": plugin_handler.turn_off}

                if action not in action_methods:
                    message = render_emojis("{emo:attention} Action not supported!")
                else:
                    try:
                        action_methods[action](plug_data)
                        message = render_emojis("{emo:check} Command sent!")
                    except Exception:
                        self._logger.exception("Caught an exception sending action to %s", plugin_id)
                        message = render_emojis("{emo:attention} Something went wrong!")

                original_command = f"{context.cmd}_{context.parameter.rsplit('_', 1)[0]}"
                command_buttons = [
                    [
                        [render_emojis("{emo:back} Back"), original_command],
                        [render_emojis("{emo:cancel} Close"), "close"],
                    ],
                ]

                self.main.send_msg(
                    message,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

    class PowerPlugin(ABC):
        def __init__(self, parent: "CmdPower"):
            self.parent = parent

        @property
        @abstractmethod
        def plugin_id(self):
            pass

        @property
        @abstractmethod
        def plugin_name(self):
            pass

        @abstractmethod
        def get_plugs_data(self):
            """
            Retrieve information about all plugs managed by this plugin.

            Returns:
                List[Dict[str, Any]]: A list of plug dictionaries, each containing:
                    - "label" (str): Human-readable plug name for display purposes.
                    - "is_on" (bool): Current power state of the plug (True if on, False if off).
                    - "data" (str): Unique identifier used to identify the plug in plugin API calls.
            """
            pass

        @abstractmethod
        def turn_on(self, plug_data):
            pass

        @abstractmethod
        def turn_off(self, plug_data):
            pass

    class DomoticzPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "domoticz"

        @property
        def plugin_name(self):
            return "Domoticz"

        def get_plugs_data(self):
            plugs_data = []

            # Domoticz plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/jneilliii/OctoPrint-Domoticz/blob/a3e1d6fddbe6a8b09faf53f62e519f8499e4cc82/octoprint_domoticz/__init__.py#L147
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "arrSmartplugs"])
            for plug in plugs:
                try:
                    ip = plug["ip"]
                    idx = plug["idx"]
                    username = plug.get("username", "")
                    password = plug.get("password", "")
                    passcode = plug.get("passcode", "")

                    label = plug.get("label") or f"{ip}|{idx}"

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
                        self.parent._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                    escaped_ip = ip.replace("|", "\\|")
                    escaped_idx = idx.replace("|", "\\|")
                    data = f"{escaped_ip}|{escaped_idx}"

                    plugs_data.append({"label": label, "is_on": is_on, "data": data})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            ip, idx = StringUtils.split_with_escape_handling(plug_data, "|")

            selected_plug = None
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "arrSmartplugs"])
            for plug in plugs:
                if plug.get("ip") == ip and plug.get("idx") == idx:
                    selected_plug = plug
                    break
            if not selected_plug:
                raise RuntimeError(f"Plug {plug_data} not found")

            username = selected_plug["username"]
            password = selected_plug["password"]
            passcode = selected_plug["passcode"]

            self.parent.main.send_octoprint_simpleapi_command(
                self.plugin_id,
                command,
                {
                    "ip": ip,
                    "idx": idx,
                    "username": username,
                    "password": password,
                    "passcode": passcode,
                },
            )

    class EnclosurePowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "enclosure"

        @property
        def plugin_name(self):
            return "Enclosure"

        def get_plugs_data(self):
            plugs_data = []

            plugs = self.parent.main.send_octoprint_request(f"/plugin/{self.plugin_id}/outputs").json()
            for plug in plugs:
                try:
                    plug_index = plug["index_id"]
                    label = plug.get("label") or plug_index
                    is_on = plug.get("State", "").strip().lower() == "on"

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_index})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command(True, plug_data)

        def turn_off(self, plug_data):
            self.send_command(False, plug_data)

        def send_command(self, status, plug_data):
            self.parent.main.send_octoprint_request(
                f"/plugin/{self.plugin_id}/outputs/{plug_data}", "PATCH", json=dict(status=status)
            )

    class GpioControlPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "gpiocontrol"

        @property
        def plugin_name(self):
            return "GPIO Control"

        def get_plugs_data(self):
            plugs_data = []

            # Gpiocontrol plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/catgiggle/OctoPrint-GpioControl/blob/37f698e51ff02493d833f43e14e88bdf54cd8b37/octoprint_gpiocontrol/__init__.py#L129
            try:
                statuses = self.parent.main.send_octoprint_simpleapi_get(self.plugin_id).json()
            except Exception:
                statuses = []
                self.parent._logger.exception("Caught an exception getting %s plugs statuses", self.plugin_id)

            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "gpio_configurations"])
            for index, configuration in enumerate(plugs):
                try:
                    label = configuration.get("name") or f"GPIO{configuration['pin']}"
                    is_on = index < len(statuses) and statuses[index].lower() == "on"

                    plugs_data.append({"label": label, "is_on": is_on, "data": index})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnGpioOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnGpioOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"id": plug_data})

    class IkeaTradfriPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "ikea_tradfri"

        @property
        def plugin_name(self):
            return "Ikea Tradfri"

        def get_plugs_data(self):
            plugs_data = []

            # Ikea_tradfri plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/ralmn/OctoPrint-Ikea-tradfri/blob/4c19c3588e3a2a85c7d78ed047062fb8d3994876/octoprint_ikea_tradfri/__init__.py#L547
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "selected_devices"])
            for plug in plugs:
                try:
                    plug_id = plug["id"]
                    label = plug.get("name") or plug_id

                    is_on = False
                    try:
                        response = self.parent.main.send_octoprint_simpleapi_command(
                            self.plugin_id, "checkStatus", {"ip": plug_id}
                        )
                        is_on = response.json().get("currentState", "").lower() == "on"
                    except Exception:
                        self.parent._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_id})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"ip": plug_data})

    class MyStromSwitchPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "mystromswitch"

        @property
        def plugin_name(self):
            return "MyStromSwitch"

        def get_plugs_data(self):
            is_on = False
            try:
                # Mystromswitch plugin has no API nor plugin functions for getting plug status, so below code is copied from the plugin code:
                # https://github.com/da4id/OctoPrint-MyStromSwitch/blob/e7bf0762d39938fb81b1d2d1945336df0e96d103/octoprint_mystromswitch/__init__.py#L180
                ip = self.parent.main._settings.global_get(["plugins", self.plugin_id, "ip"])
                token = self.parent.main._settings.global_get(["plugins", self.plugin_id, "token"])

                response = requests.get(f"http://{ip}/report", headers={"Token": token}, timeout=5)
                is_on = response.json().get("relay", False)
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s status", self.plugin_id)

            # Mystromswitch is single plug, so data below is dummy
            return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

        def turn_on(self, plug_data):
            self.send_command("enableRelais")

        def turn_off(self, plug_data):
            self.send_command("disableRelais")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command)

    class OctoHuePowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "octohue"

        @property
        def plugin_name(self):
            return "OctoHue"

        def get_plugs_data(self):
            is_on = False
            try:
                response = self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, "getstate")
                is_on = response.json().get("on", False)
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s status", self.plugin_id)

            # Octohue is single plug, so data below is dummy
            return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

        def turn_on(self, plug_data):
            self.send_command("turnon")

        def turn_off(self, plug_data):
            self.send_command("turnoff")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command)

    class OctoLightPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "octolight"

        @property
        def plugin_name(self):
            return "OctoLight"

        def get_plugs_data(self):
            is_on = False
            try:
                response = self.parent.main.send_octoprint_simpleapi_get(self.plugin_id)
                is_on = response.json().get("state", False)
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s status", self.plugin_id)

            # Octolight is single plug, so data below is dummy
            return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

        def turn_on(self, plug_data):
            self.send_command("turnOn")

        def turn_off(self, plug_data):
            self.send_command("turnOff")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command)

    class OctoLightHAPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "octolightHA"

        @property
        def plugin_name(self):
            return "OctoLight HA"

        def get_plugs_data(self):
            is_on = False
            try:
                response = self.parent.main.send_octoprint_simpleapi_get(self.plugin_id, dict(action="getState"))
                is_on = response.json().get("state", False)
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s status", self.plugin_id)

            # OctolightHA is single plug, so data below is dummy
            return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

        def turn_on(self, plug_data):
            self.send_command("turnOn")

        def turn_off(self, plug_data):
            self.send_command("turnOff")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_get(self.plugin_id, dict(action=command))

    class OctoRelayPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "octorelay"

        @property
        def plugin_name(self):
            return "OctoRelay"

        def get_plugs_data(self):
            plugs_data = []

            plugs = self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, "listAllStatus").json()
            for plug in plugs:
                try:
                    plug_id = plug["id"]
                    label = plug.get("name") or f"RELAY{plug_id}"
                    is_on = plug.get("status", False)

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_id})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command(plug_data, True)

        def turn_off(self, plug_data):
            self.send_command(plug_data, False)

        def send_command(self, plug_data, target):
            self.parent.main.send_octoprint_simpleapi_command(
                self.plugin_id, "update", {"subject": plug_data, "target": target}
            )

    class OrviboS20PowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "orvibos20"

        @property
        def plugin_name(self):
            return "OrviboS20"

        def get_plugs_data(self):
            plugs_data = []

            # OrviboS20 plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/cprasmu/OctoPrint-OrviboS20/blob/a40d0ad4184e48781ff1ebc7fb108eba1e084ba8/octoprint_orvibos20/__init__.py#L500
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "arrSmartplugs"])
            for plug in plugs:
                try:
                    plug_ip = plug["ip"]
                    label = plug.get("label") or plug_ip

                    is_on = False
                    try:
                        # OrviboS20 plugin has no API for getting plug status, so we need to use the plugin functions
                        plugin_module = self.parent.main._plugin_manager.get_plugin(self.plugin_id, True)
                        is_on = plugin_module.Orvibo.discover(plug_ip).on
                    except Exception:
                        self.parent._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_ip})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"ip": plug_data})

    class PSUControlPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "psucontrol"

        @property
        def plugin_name(self):
            return "PSU Control"

        def get_plugs_data(self):
            is_on = False
            try:
                response = self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, "getPSUState")
                is_on = response.json().get("isPSUOn", False)
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s status", self.plugin_id)

            # Psucontrol is single plug, so data below is dummy
            return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

        def turn_on(self, plug_data):
            self.send_command("turnPSUOn")

        def turn_off(self, plug_data):
            self.send_command("turnPSUOff")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command)

    class TasmotaPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "tasmota"

        @property
        def plugin_name(self):
            return "Tasmota"

        def get_plugs_data(self):
            plugs_data = []

            # Tasmota plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/jneilliii/OctoPrint-Tasmota/blob/49c7e01f4a077d0d650931fd91f3b63cfef780c2/octoprint_tasmota/__init__.py#L816
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "arrSmartplugs"])
            for plug in plugs:
                try:
                    plug_ip = plug["ip"]
                    plug_idx = plug["idx"]
                    label = plug.get("label") or f"{plug_ip}|{plug_idx}"

                    is_on = False
                    try:
                        response = self.parent.main.send_octoprint_simpleapi_command(
                            self.plugin_id, "checkStatus", {"ip": plug_ip, "idx": plug_idx}
                        )
                        is_on = response.json().get("currentState", "").lower() == "on"
                    except Exception:
                        self.parent._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                    escaped_ip = plug_ip.replace("|", "\\|")
                    escaped_idx = plug_idx.replace("|", "\\|")
                    data = f"{escaped_ip}|{escaped_idx}"

                    plugs_data.append({"label": label, "is_on": is_on, "data": data})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            ip, idx = StringUtils.split_with_escape_handling(plug_data, "|")
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"ip": ip, "idx": idx})

    class TasmotaMQTTPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "tasmota_mqtt"

        @property
        def plugin_name(self):
            return "TasmotaMQTT"

        def get_plugs_data(self):
            plugs_data = []

            plugs = self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, "getListPlug").json()
            for plug in plugs:
                try:
                    is_on = plug.get("currentstate", "").lower() == "on"

                    label = plug.get("label") or f"{plug['topic']}|{plug['relayN']}"

                    escaped_topic = plug["topic"].replace("|", "\\|")
                    escaped_relay = plug["relayN"].replace("|", "\\|")
                    data = f"{escaped_topic}|{escaped_relay}"

                    plugs_data.append({"label": label, "is_on": is_on, "data": data})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            topic, relay_n = StringUtils.split_with_escape_handling(plug_data, "|")
            self.parent.main.send_octoprint_simpleapi_command(
                self.plugin_id, command, {"topic": topic, "relayN": relay_n}
            )

    class TPLinkSmartplugPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "tplinksmartplug"

        @property
        def plugin_name(self):
            return "TPLinkSmartplug"

        def get_plugs_data(self):
            plugs_data = []

            plugs = self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, "getListPlug").json()
            for plug in plugs:
                try:
                    plug_ip = plug["ip"]
                    label = plug.get("label") or plug_ip
                    is_on = plug.get("currentState", "").lower() == "on"

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_ip})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"ip": plug_data})

    class TuyaSmartplugPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "tuyasmartplug"

        @property
        def plugin_name(self):
            return "TuyaSmartplug"

        def get_plugs_data(self):
            plugs_data = []

            # Tuyasmartplug plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/ziirish/OctoPrint-TuyaSmartplug/blob/4344aeb6d9d59f4979d326a710656121d247e9af/octoprint_tuyasmartplug/__init__.py#L240
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "arrSmartplugs"])
            for plug in plugs:
                try:
                    label = plug["label"]

                    is_on = False
                    try:
                        # Tuyasmartplug plugin has no API for getting plug status, so we need to use the plugin functions
                        plugin_implementation = self.parent.main._plugin_manager.plugins[self.plugin_id].implementation
                        is_on = plugin_implementation.is_turned_on(pluglabel=label)
                    except Exception:
                        self.parent._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                    plugs_data.append({"label": label, "is_on": is_on, "data": label})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"label": plug_data})

    class USBRelayControlPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "usbrelaycontrol"

        @property
        def plugin_name(self):
            return "USB Relay Control"

        def get_plugs_data(self):
            plugs_data = []

            # Usbrelaycontrol plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/abudden/OctoPrint-USBRelayControl/blob/0f06bccc06107f2b76fe360fed63698472c483cc/octoprint_usbrelaycontrol/__init__.py#L135
            try:
                statuses = self.parent.main.send_octoprint_simpleapi_get(self.plugin_id).json()
            except Exception:
                statuses = []
                self.parent._logger.exception("Caught an exception getting %s plugs statuses", self.plugin_id)

            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "usbrelay_configurations"])
            for index, configuration in enumerate(plugs):
                try:
                    label = configuration["name"] or f"RELAY{configuration['relaynumber']}"
                    is_on = index < len(statuses) and statuses[index].lower() == "on"

                    plugs_data.append({"label": label, "is_on": is_on, "data": index})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnUSBRelayOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnUSBRelayOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"id": plug_data})

    class WemoSwitchPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "wemoswitch"

        @property
        def plugin_name(self):
            return "WemoSwitch"

        def get_plugs_data(self):
            plugs_data = []

            # Wemoswitch plugin has no API for getting plugs. Below code is copied from the plugin code:
            # https://github.com/jneilliii/OctoPrint-WemoSwitch/blob/70500edbff7eeda65efecc105f573e546cb8d661/octoprint_wemoswitch/__init__.py#L247
            plugs = self.parent.main._settings.global_get(["plugins", self.plugin_id, "arrSmartplugs"])
            for plug in plugs:
                try:
                    plug_ip = plug["ip"]
                    label = plug["label"] or plug_ip

                    is_on = False
                    try:
                        # Wemoswitch plugin has no API for getting plug status, so we need to use the plugin functions
                        plugin_implementation = self.parent.main._plugin_manager.plugins[self.plugin_id].implementation
                        chk = plugin_implementation.sendCommand("info", plug_ip)
                        is_on = chk == 1 or chk == 8
                    except Exception:
                        self.parent._logger.exception("Caught an exception getting %s plug status", self.plugin_id)

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_ip})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turnOn", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turnOff", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"ip": plug_data})

    class WledPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "wled"

        @property
        def plugin_name(self):
            return "WLED"

        def get_plugs_data(self):
            is_on = False
            try:
                response = self.parent.main.send_octoprint_simpleapi_get(self.plugin_id)
                is_on = response.json().get("lights_on", False)
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s status", self.plugin_id)

            # Wled is single plug, so data below is dummy
            return [{"label": self.plugin_name, "is_on": is_on, "data": self.plugin_id}]

        def turn_on(self, plug_data):
            self.send_command("lights_on")

        def turn_off(self, plug_data):
            self.send_command("lights_off")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command)

    class WS281xPowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "ws281x_led_status"

        @property
        def plugin_name(self):
            return "WS281x"

        def get_plugs_data(self):
            plugs_data = []

            plugs_names = ["lights", "torch"]

            statuses = {}
            try:
                statuses = self.parent.main.send_octoprint_simpleapi_get(self.plugin_id).json()
            except Exception:
                self.parent._logger.exception("Caught an exception getting %s plugs statuses", self.plugin_id)

            for plug_name in plugs_names:
                try:
                    label = f"{self.plugin_name} {plug_name}"
                    is_on = statuses.get(f"{plug_name}_on", False)

                    plugs_data.append({"label": label, "is_on": is_on, "data": plug_name})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command(f"{plug_data}_on")

        def turn_off(self, plug_data):
            self.send_command(f"{plug_data}_off")

        def send_command(self, command):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command)

    class WyzePowerPlugin(PowerPlugin):
        @property
        def plugin_id(self):
            return "wyze"

        @property
        def plugin_name(self):
            return "Wyze"

        def get_plugs_data(self):
            plugs_data = []

            plugs = self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, "get_devices").json()
            for plug in plugs:
                try:
                    label = plug["device_name"]
                    is_on = False  # Wyze plugin does not support retrieving plugs status
                    device_mac = plug["device_mac"]

                    plugs_data.append({"label": label, "is_on": is_on, "data": device_mac})
                except Exception:
                    self.parent._logger.exception("Caught an exception processing %s plug data", self.plugin_id)

            return plugs_data

        def turn_on(self, plug_data):
            self.send_command("turn_on", plug_data)

        def turn_off(self, plug_data):
            self.send_command("turn_off", plug_data)

        def send_command(self, command, plug_data):
            self.parent.main.send_octoprint_simpleapi_command(self.plugin_id, command, {"device_mac": plug_data})
