import hashlib
import html
import time

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

try:
    from octoprint.printer.connection import ConnectedPrinter
except ImportError:
    # On OctoPrint < 2.0.0 there are no connectors
    ConnectedPrinter = None

render_emojis = Emoji.render_emojis


class CmdCon(BaseCommand):
    # How long to wait for a connection attempt to succeed before giving up.
    CONNECTION_TIMEOUT = 15  # Seconds

    # Substrings (case-insensitive) of connection parameter keys whose values must never
    # be displayed in chat messages
    SENSITIVE_PARAM_KEYWORDS = ("key", "password", "psw")

    def execute(self, context: CommandContext):
        if context.parameter:
            action, *params = context.parameter.split("_")
            actions = {
                "c": self.connect,
                "d": self.disconnect,
            }
            if action in actions:
                actions[action](context, params)
            return

        if ConnectedPrinter is not None:
            connection_state = self.main._printer.connection_state

            # Status
            status_str = str(connection_state.get("state", "Offline"))

            # Connector name
            connector_id = connection_state.get("connector")
            connector_str = connector_id or "Unknown"
            if connector_id:
                connector_class = ConnectedPrinter.find(connector_id)
                if connector_class is not None and getattr(connector_class, "name", None):
                    connector_str = connector_class.name

            # Connector params
            meta_keys = {"connector", "state", "profile", "printer_capabilities"}
            connector_params_str = ""
            for key, value in connection_state.items():
                if key in meta_keys:
                    continue
                label = key.replace("_", " ").title()
                display = "***" if self._is_sensitive_param(key) else str(value)
                connector_params_str += f"<b>{html.escape(label)}</b>: {html.escape(display)}\n"

            # Profile
            profile = connection_state.get("profile")
            profile_str = str(profile.get("name")) if isinstance(profile, dict) else str(profile)

        else:
            # OctoPrint < 2.0.0: connectors didn't exist, fall back Serial Connection.

            # nosemgrep (this is a fallback for older OctoPrint versions)
            status, port, baudrate, profile = self.main._printer.get_current_connection()

            # Status
            status_str = str(status)

            # Connector name
            connector_str = "Serial Connection"

            # Connector params
            port_str = str(port)
            baud_str = "AUTO" if str(baudrate) == "0" else str(baudrate)
            connector_params_str = f"<b>Port</b>: {html.escape(port_str)}\n<b>Baudrate</b>: {html.escape(baud_str)}\n"

            # Profile
            profile_str = str(profile.get("name")) if profile is not None else "None"

        # Build message
        status_dot = "{emo:online}" if self.main._printer.is_operational() else "{emo:offline}"
        msg = render_emojis(
            f"{{emo:info}} <b>Connection information</b>\n\n<b>Status</b>: {html.escape(status_str)} {status_dot}\n\n"
        )
        if not self.main._printer.is_closed_or_error():
            msg += render_emojis(
                f"<b>Connector</b>: {html.escape(connector_str)}\n"
                f"{connector_params_str}\n"
                f"<b>Profile</b>: {html.escape(profile_str)}"
            )

        # Build buttons
        btn_close = [render_emojis("{emo:cancel} Close"), "close"]
        if self.main._printer.is_closed_or_error():
            btn_connect = [render_emojis("{emo:online} Connect"), f"{context.cmd}_c"]
            command_buttons = [[btn_connect, btn_close]]
        elif (
            self.main._printer.is_printing()
            or self.main._printer.is_pausing()
            or self.main._printer.is_paused()
            or self.main._printer.is_resuming()
            or self.main._printer.is_cancelling()
            or self.main._printer.is_finishing()
        ):
            msg += render_emojis("\n\n{emo:warning} You can't disconnect while printing.")
            command_buttons = [[btn_close]]
        else:
            btn_disconnect = [render_emojis("{emo:offline} Disconnect"), f"{context.cmd}_d"]
            command_buttons = [[btn_disconnect, btn_close]]

        # Send message
        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def disconnect(self, context: CommandContext, params):
        self.main._printer.disconnect()

        msg = render_emojis("{emo:check} Printer disconnected.")

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

    def connect(self, context: CommandContext, params):
        if params:
            if params[0] == "d":  # Default Connection
                connection_data = self.ask_default_connection_data(context, params[1:])
            elif params[0] == "s" and self._is_serial_connection_available():  # Serial Connection
                connection_data = self.ask_serial_connection_data(context, params[1:])
            else:
                return

            # Connection data still needs more user input
            # (a message asking for the next parameter has already been sent)
            if connection_data is None:
                return

            self.main.send_msg(
                render_emojis("{emo:info} Connecting..."),
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )

            parameters = connection_data.get("parameters")
            self.main._printer.connect(
                connector=connection_data.get("connector"),
                parameters=parameters,
                profile=connection_data.get("profile"),
                port=parameters.get("port"),
                baudrate=parameters.get("baudrate"),
            )

            start_time = time.time()
            while time.time() - start_time < self.CONNECTION_TIMEOUT:
                if self.main._printer.is_operational() or self.main._printer.is_error():
                    break
                time.sleep(1)

            if self.main._printer.is_operational():
                msg = render_emojis("{emo:check} Connection established.")
            else:
                current_state = str(self.main._printer.get_state_string())
                msg = render_emojis(
                    "{emo:attention} Failed to start connection.\n"
                    f"Current state: <code>{html.escape(current_state)}</code>."
                )

            command_buttons = [[[render_emojis("{emo:back} Back"), f"{context.cmd}"]]]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

        else:
            msg = render_emojis("{emo:question} How do you want to connect?")

            command_buttons = [
                [
                    [render_emojis("{emo:lamp} Use Default Connection"), f"{context.cmd}_c_d"],
                ],
            ]
            if self._is_serial_connection_available():
                command_buttons.append([[render_emojis("{emo:edit} Use Serial Connection"), f"{context.cmd}_c_s"]])
            command_buttons.append([[render_emojis("{emo:back} Back"), context.cmd]])

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def ask_default_connection_data(self, context: CommandContext, params):
        all_profiles = self.main._printer_profile_manager.get_all()
        profile_ids = list(all_profiles.keys())

        preferred_connector = None
        preferred_parameters = {}
        if ConnectedPrinter is not None:
            preferred_connector = self.main._settings.global_get(["printerConnection", "preferred", "connector"])
            preferred_parameters = (
                self.main._settings.global_get(["printerConnection", "preferred", "parameters"]) or {}
            )

        # Step 1: ask profile (skip if at most one available)
        if not params:
            if len(profile_ids) <= 1:
                return {
                    "connector": preferred_connector,
                    "parameters": preferred_parameters,
                    "profile": profile_ids[0] if profile_ids else None,
                }
            self._ask_choice(
                context,
                parent=f"{context.cmd}_c",
                callback_prefix=f"{context.cmd}_c_d",
                msg=self._build_connection_summary(preferred_connector, preferred_parameters)
                + render_emojis("{emo:question} Select the printer profile to use."),
                options=[(p["id"], p["name"]) for p in all_profiles.values()],
                item_emoji="profile",
            )
            return None

        profile_id = next(
            profile["id"] for profile in all_profiles.values() if self._hash_parameter(profile["id"]) == params[0]
        )

        return {
            "connector": preferred_connector,
            "parameters": preferred_parameters,
            "profile": profile_id,
        }

    def ask_serial_connection_data(self, context: CommandContext, params):
        if ConnectedPrinter is not None:
            serial_connector = ConnectedPrinter.find("serial")
            connection_options = serial_connector.connection_options() if serial_connector else {}

            ports = connection_options.get("port", [])
            baudrates = connection_options.get("baudrate", [])
        else:
            # OctoPrint < 2.0.0 backwards compatibility

            # nosemgrep (this is a fallback for older OctoPrint versions)
            connection_options = self.main._printer.get_connection_options()

            ports = connection_options["ports"]
            baudrates = connection_options["baudrates"]

        all_profiles = self.main._printer_profile_manager.get_all()
        profile_ids = list(all_profiles.keys())

        # Step 1: ask port
        if len(params) < 1:
            self._ask_choice(
                context,
                parent=f"{context.cmd}_c",
                callback_prefix=f"{context.cmd}_c_s",
                msg=render_emojis("{emo:question} Select the port to connect to."),
                options=[(p, p) for p in ports],
                item_emoji="port",
                with_auto=True,
            )
            return None

        port = self._resolve_hashed(params[0], ports)

        # Step 2: ask baudrate
        if len(params) < 2:
            self._ask_choice(
                context,
                parent=f"{context.cmd}_c_s",
                callback_prefix=f"{context.cmd}_c_s_{params[0]}",
                msg=render_emojis("{emo:question} Select the baudrate to use."),
                options=[(b, b) for b in baudrates],
                item_emoji="speed",
                with_auto=True,
            )
            return None

        baudrate = self._resolve_hashed(params[1], baudrates)

        # Step 3: ask profile (skip if at most one available)
        if len(params) < 3:
            if len(profile_ids) <= 1:
                return {
                    "connector": "serial",
                    "parameters": {"port": port, "baudrate": baudrate},
                    "profile": profile_ids[0] if profile_ids else None,
                }
            self._ask_choice(
                context,
                parent=f"{context.cmd}_c_s_{params[0]}",
                callback_prefix=f"{context.cmd}_c_s_{params[0]}_{params[1]}",
                msg=self._build_connection_summary("serial", {"port": port, "baudrate": baudrate})
                + render_emojis("{emo:question} Select the printer profile to use."),
                options=[(p["id"], p["name"]) for p in all_profiles.values()],
                item_emoji="profile",
            )
            return None

        profile_id = next(
            profile["id"] for profile in all_profiles.values() if self._hash_parameter(profile["id"]) == params[2]
        )

        return {
            "connector": "serial",
            "parameters": {"port": port, "baudrate": baudrate},
            "profile": profile_id,
        }

    def _ask_choice(self, context: CommandContext, parent, callback_prefix, msg, options, item_emoji, with_auto=False):
        buttons = []
        if with_auto:
            buttons.append([render_emojis("{emo:lamp} AUTO"), f"{callback_prefix}_AUTO"])
        for value, label in options:
            buttons.append(
                [
                    render_emojis(f"{{emo:{item_emoji}}} {label}"),
                    f"{callback_prefix}_{self._hash_parameter(value)}",
                ]
            )
        command_buttons = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
        command_buttons.append([[render_emojis("{emo:back} Back"), parent]])

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def _resolve_hashed(self, value, choices):
        if value == "AUTO":
            return None
        return next(c for c in choices if self._hash_parameter(c) == value)

    def _build_connection_summary(self, connector, parameters):
        connector_label = "Default"
        if connector:
            connector_label = connector
            if ConnectedPrinter is not None:
                connector_class = ConnectedPrinter.find(connector)
                if connector_class is not None and getattr(connector_class, "name", None):
                    connector_label = connector_class.name

        lines = [
            render_emojis("{emo:info} You are about to connect with:"),
            "",
            f"<b>Connector</b>: {html.escape(str(connector_label))}",
        ]
        for key, value in (parameters or {}).items():
            label = key.replace("_", " ").title()
            if self._is_sensitive_param(key):
                display = "***"
            else:
                display = str(value) if value is not None else "AUTO"
            lines.append(f"<b>{html.escape(label)}</b>: {html.escape(display)}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _is_serial_connection_available(self):
        # Serial connection is always available on OctoPrint < 2.0.0 (no connectors at all)
        # or when the serial_connector plugin is installed and enabled on >= 2.0.0.
        return ConnectedPrinter is None or self.main._plugin_manager.get_plugin("serial_connector", True) is not None

    def _is_sensitive_param(self, key):
        key_lower = str(key).lower()
        return any(keyword in key_lower for keyword in self.SENSITIVE_PARAM_KEYWORDS)

    def _hash_parameter(self, parameter):
        # Telegram callback_data is limited to 64 bytes, so we truncate the
        # md5 hex digest to keep the resulting callback strings short enough.
        # The longest callback we build is "/con_c_s_<port>_<baud>_<profile>"
        # (11 fixed chars + 3 hashes), so 16 hex chars per hash fits safely.
        return hashlib.md5(str(parameter).encode()).hexdigest()[:16]
