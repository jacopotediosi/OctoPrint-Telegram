import hashlib
import html
import time

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdCon(BaseCommand):
    CONNECTION_TIMEOUT = 15  # Seconds

    temp_connection_settings = {}

    def execute(self, context: CommandContext):
        if context.parameter:
            action, *params = context.parameter.split("_")
            actions = {
                "s": self.settings,
                "c": self.connect,
                "d": self.disconnect,
            }
            if action in actions:
                actions[action](context, params)
            return

        status, port, baudrate, profile = self.main._printer.get_current_connection()
        connection_options = self.main._printer.get_connection_options()

        status_str = str(status)
        port_str = str(port)
        baud_str = "AUTO" if str(baudrate) == "0" else str(baudrate)
        profile_str = str(profile.get("name")) if profile is not None else "None"
        autoconnect_str = str(connection_options.get("autoconnect"))

        msg = render_emojis(
            "{emo:info} <b>Connection information</b>\n\n"
            f"<b>Status</b>: {html.escape(status_str)}\n\n"
            f"<b>Port</b>: {html.escape(port_str)}\n"
            f"<b>Baud</b>: {html.escape(baud_str)}\n"
            f"<b>Profile</b>: {html.escape(profile_str)}\n"
            f"<b>AutoConnect</b>: {html.escape(autoconnect_str)}\n\n"
        )

        btn_defaults = [render_emojis("{emo:star} Defaults"), f"{context.cmd}_s"]
        btn_close = [render_emojis("{emo:cancel} Close"), "close"]

        if self.main._printer.is_operational():
            if not self.main._printer.is_ready():
                msg += render_emojis("{emo:warning} You can't disconnect while printing.")
                command_buttons = [[btn_defaults, btn_close]]
            else:
                btn_disconnect = [render_emojis("{emo:offline} Disconnect"), f"{context.cmd}_d"]
                command_buttons = [[btn_disconnect, btn_defaults, btn_close]]
        else:
            btn_connect = [render_emojis("{emo:online} Connect"), f"{context.cmd}_c"]
            command_buttons = [[btn_connect, btn_defaults, btn_close]]

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def settings(self, context: CommandContext, params):
        if params:
            param_handlers = {
                "p": self.configure_port,
                "b": self.configure_baudrate,
                "pr": self.configure_profile,
                "a": self.configure_autoconnect,
            }
            handler = param_handlers.get(params[0])
            if handler:
                handler(context, params[1:], "s")
        else:
            connection_options = self.main._printer.get_connection_options()
            profile = self.main._printer_profile_manager.get_default()

            port_str = str(connection_options.get("portPreference"))
            baud_str = str(connection_options.get("baudratePreference") or "AUTO")
            profile_name_str = str(profile.get("name")) if profile is not None else "None"
            autoconnect_str = str(connection_options.get("autoconnect"))

            msg = render_emojis(
                "{emo:settings} Default connection settings\n"
                f"\n{{emo:port}} <b>Port</b>: {html.escape(port_str)}"
                f"\n{{emo:speed}} <b>Baud</b>: {html.escape(baud_str)}"
                f"\n{{emo:profile}} <b>Profile</b>: {html.escape(profile_name_str)}"
                f"\n{{emo:lamp}} <b>AutoConnect</b>: {html.escape(autoconnect_str)}"
            )

            command_buttons = [
                [
                    [render_emojis("{emo:port} Port"), f"{context.cmd}_s_p"],
                    [render_emojis("{emo:speed} Baud"), f"{context.cmd}_s_b"],
                    [
                        render_emojis("{emo:profile} Profile"),
                        f"{context.cmd}_s_pr",
                    ],
                    [render_emojis("{emo:lamp} AutoConnect"), f"{context.cmd}_s_a"],
                ],
                [
                    [
                        render_emojis("{emo:back} Back"),
                        context.cmd,
                    ]
                ],
            ]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def configure_port(self, context: CommandContext, params, parent):
        if params:
            if params[0] == "AUTO":
                port = "AUTO"
            else:
                port = next(
                    port
                    for port in self.main._printer.get_connection_options()["ports"]
                    if self.hash_parameter(port) == params[0]
                )

            self.main._settings.global_set(["serial", "port"], port)
            self.main._settings.save()
            self.settings(context, [])
        else:
            con = self.main._printer.get_connection_options()

            current_setting = str(con.get("portPreference") or "AUTO")
            msg = render_emojis(
                f"{{emo:question}} Select default port.\nCurrent setting: <code>{html.escape(current_setting)}</code>"
            )

            command_buttons = []

            port_buttons = [[render_emojis("{emo:lamp} AUTO"), f"{context.cmd}_{parent}_p_AUTO"]]
            for port in con["ports"]:
                port_buttons.append(
                    [render_emojis(f"{{emo:port}} {port}"), f"{context.cmd}_{parent}_p_{self.hash_parameter(port)}"]
                )
            for i in range(0, len(port_buttons), 3):
                command_buttons.append(port_buttons[i : i + 3])

            command_buttons.append(
                [
                    [
                        render_emojis("{emo:back} Back"),
                        f"{context.cmd}_{parent}",
                    ]
                ]
            )

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def configure_baudrate(self, context: CommandContext, params, parent):
        if params:
            if params[0] == "AUTO":
                baudrate = 0
            else:
                baudrate = next(
                    baudrate
                    for baudrate in self.main._printer.get_connection_options()["baudrates"]
                    if self.hash_parameter(baudrate) == params[0]
                )

            self.main._settings.global_set_int(["serial", "baudrate"], baudrate)
            self.main._settings.save()
            self.settings(context, [])
        else:
            con = self.main._printer.get_connection_options()

            current_setting = str(con.get("baudratePreference") or "AUTO")
            msg = render_emojis(
                "{emo:question} Select default baudrate.\n"
                f"Current setting: <code>{html.escape(current_setting)}</code>"
            )

            command_buttons = []

            baud_buttons = [[render_emojis("{emo:lamp} AUTO"), f"{context.cmd}_{parent}_b_AUTO"]]
            for baudrate in con["baudrates"]:
                baud_buttons.append(
                    [
                        render_emojis(f"{{emo:speed}} {baudrate}"),
                        f"{context.cmd}_{parent}_b_{self.hash_parameter(baudrate)}",
                    ]
                )
            for i in range(0, len(baud_buttons), 3):
                command_buttons.append(baud_buttons[i : i + 3])

            command_buttons.append(
                [
                    [
                        render_emojis("{emo:back} Back"),
                        f"{context.cmd}_{parent}",
                    ]
                ]
            )

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def configure_profile(self, context: CommandContext, params, parent):
        if params:
            profile_id = next(
                profile["id"]
                for profile in self.main._printer_profile_manager.get_all().values()
                if self.hash_parameter(profile["id"]) == params[0]
            )

            self.main._settings.global_set(["printerProfiles", "default"], profile_id)
            self.main._settings.save()
            self.settings(context, [])
        else:
            all_profiles = self.main._printer_profile_manager.get_all()
            default_profile = self.main._printer_profile_manager.get_default()

            current_setting = str(default_profile["name"])
            msg = render_emojis(
                "{emo:question} Select default profile.\n"
                f"Current setting: <code>{html.escape(current_setting)}</code>"
            )

            command_buttons = []

            profile_buttons = []
            for profile in all_profiles.values():
                profile_buttons.append(
                    [
                        render_emojis(f"{{emo:profile}} {profile['name']}"),
                        f"{context.cmd}_{parent}_pr_{self.hash_parameter(profile['id'])}",
                    ]
                )
            for i in range(0, len(profile_buttons), 3):
                command_buttons.append(profile_buttons[i : i + 3])

            command_buttons.append(
                [
                    [
                        render_emojis("{emo:back} Back"),
                        f"{context.cmd}_{parent}",
                    ]
                ]
            )

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def configure_autoconnect(self, context: CommandContext, params, parent):
        if params:
            self.main._settings.global_set_boolean(["serial", "autoconnect"], params[0])
            self.main._settings.save()
            self.settings(context, [])
        else:
            connection_options = self.main._printer.get_connection_options()

            current_setting = str(connection_options["autoconnect"])
            msg = render_emojis(
                "{emo:question} AutoConnect on startup?\n"
                f"Current setting: <code>{html.escape(current_setting)}</code>"
            )

            command_buttons = [
                [
                    [render_emojis("{emo:check} ON"), f"{context.cmd}_s_a_true"],
                    [render_emojis("{emo:cancel} OFF"), f"{context.cmd}_s_a_false"],
                ],
                [
                    [
                        render_emojis("{emo:back} Back"),
                        f"{context.cmd}_{parent}",
                    ]
                ],
            ]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def connect(self, context: CommandContext, params):
        if params:
            if params[0] == "a":  # Auto connection
                self.temp_connection_settings = {
                    "port": None,
                    "baudrate": None,
                    "profile": None,
                }
            elif params[0] == "d":  # Default connection
                self.temp_connection_settings = {
                    "port": self.main._settings.global_get(["serial", "port"]),
                    "baudrate": self.main._settings.global_get(["serial", "baudrate"]),
                    "profile": self.main._printer_profile_manager.get_default()["name"],
                }
            elif params[0] == "p" and len(params) < 2:  # Manual port selection
                self.configure_port(context, [], "c")
                return
            elif params[0] == "p":  # Port selected, now choose baudrate
                if params[1] == "AUTO":
                    port = "AUTO"
                else:
                    port = next(
                        port
                        for port in self.main._printer.get_connection_options()["ports"]
                        if self.hash_parameter(port) == params[1]
                    )
                self.temp_connection_settings["port"] = port
                self.configure_baudrate(context, [], "c")
                return
            elif params[0] == "b":  # Baudrate selected, now choose profile
                if params[1] == "AUTO":
                    baudrate = 0
                else:
                    baudrate = next(
                        baudrate
                        for baudrate in self.main._printer.get_connection_options()["baudrates"]
                        if self.hash_parameter(baudrate) == params[1]
                    )
                self.temp_connection_settings["baudrate"] = baudrate
                self.configure_profile(context, [], "c")
                return
            elif params[0] == "pr":  # Profile selected, ready to connect
                profile_id = next(
                    profile["id"]
                    for profile in self.main._printer_profile_manager.get_all().values()
                    if self.hash_parameter(profile["id"]) == params[1]
                )
                self.temp_connection_settings["profile"] = profile_id

            self.main.send_msg(
                render_emojis("{emo:info} Connecting..."),
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )

            self.main._printer.connect(
                port=self.temp_connection_settings["port"],
                baudrate=self.temp_connection_settings["baudrate"],
                profile=self.temp_connection_settings["profile"],
            )

            wait_states = [
                "Offline",
                "Detecting baudrate",
                "Connecting",
                "Opening serial port",
                "Detecting serial port",
                "Detecting serial connection",
                "Opening serial connection",
            ]

            start_time = time.time()
            timeout = self.CONNECTION_TIMEOUT

            current_state = "Unknown"
            while time.time() - start_time < timeout:
                try:
                    con = self.main._printer.get_current_connection()
                    current_state = str(con[0])

                    if current_state not in wait_states:
                        break
                except Exception:
                    pass

                time.sleep(1)

            if current_state == "Operational":
                msg = render_emojis("{emo:check} Connection established.")
            else:
                msg = render_emojis(
                    "{emo:attention} Failed to start connection.\n"
                    f"Current state: <code>{html.escape(current_state)}</code>."
                )

            command_buttons = [
                [
                    [
                        render_emojis("{emo:back} Back"),
                        f"{context.cmd}",
                    ]
                ]
            ]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )
        else:
            msg = render_emojis("{emo:question} Select connection option.")

            command_buttons = [
                [
                    [render_emojis("{emo:lamp} AUTO"), f"{context.cmd}_c_a"],
                    [render_emojis("{emo:star} Default"), f"{context.cmd}_c_d"],
                ],
                [
                    [render_emojis("{emo:edit} Manual"), f"{context.cmd}_c_p"],
                    [
                        render_emojis("{emo:back} Back"),
                        context.cmd,
                    ],
                ],
            ]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def disconnect(self, context: CommandContext, params):
        self.main._printer.disconnect()

        msg = render_emojis("{emo:info} Printer disconnected.")

        command_buttons = [
            [
                [
                    render_emojis("{emo:back} Back"),
                    f"{context.cmd}",
                ]
            ]
        ]

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def hash_parameter(self, parameter):
        return hashlib.md5(str(parameter).encode()).hexdigest()
