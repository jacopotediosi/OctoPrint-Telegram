from __future__ import annotations

import html
import time
from typing import Sequence

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState, StaleMenuError
from .base import BaseCommand, CommandContext

try:
    from octoprint.printer.connection import ConnectedPrinter
except ImportError:
    # On OctoPrint < 2.0.0 there are no connectors
    ConnectedPrinter = None

render_emojis = Emoji.render_emojis


class ConMenuState(MenuState):
    """The options the menu offers and the connection settings picked so far."""

    def __init__(
        self,
        options: list[str | int | None],
        port: str | int | None = None,
        baudrate: str | int | None = None,
    ) -> None:
        """Set up the options the menu offers and the connection settings picked so far.

        Args:
            options (list[str | int | None]): The value behind each option, in the order they are offered.
            port (str | int | None, optional): The port picked so far, or None for AUTO.
            baudrate (str | int | None, optional): The baudrate picked so far, or None for AUTO.
        """
        self.options = options
        self.port = port
        self.baudrate = baudrate


class CmdCon(BaseCommand):
    # How long to wait for a connection attempt to succeed before giving up.
    CONNECTION_TIMEOUT = 15  # Seconds

    # Substrings (case-insensitive) of connection parameter keys whose values must never
    # be displayed in chat messages
    SENSITIVE_PARAM_KEYWORDS = ("key", "password", "psw")

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Connect the printer or disconnect it.

        Possible callback queries, where {position} stands for the position of an option in the list:

        - /con -> show the connection information
        - /con_disconnect -> disconnect the printer
        - /con_connect -> ask whether to connect with the default connection or with a serial one
        - /con_connect_default -> connect with the default connection, or ask which printer profile to use
        - /con_connect_default_{position} -> connect with the default connection and the profile at that position
        - /con_connect_serial -> ask which port to connect to
        - /con_connect_serial_port_{position} -> take the port at that position and ask which baudrate to use
        - /con_connect_serial_baudrate -> go back to asking which baudrate to use
        - /con_connect_serial_baudrate_{position} -> take the baudrate at that position, then connect or ask
          which printer profile to use
        - /con_connect_serial_profile_{position} -> connect over serial with the profile at that position
        """
        if command_context.parameter:
            action, *params = command_context.parameter.split("_")
            actions = {
                "connect": self._connect,
                "disconnect": self._disconnect,
            }
            if action in actions:
                actions[action](command_context, params)
            return

        if ConnectedPrinter is not None:
            connection_state = self.plugin_context.printer.connection_state

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
            status, port, baudrate, profile = self.plugin_context.printer.get_current_connection()

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
        status_dot = "{emo:online}" if self.plugin_context.printer.is_operational() else "{emo:offline}"
        msg = render_emojis(
            f"{{emo:info}} <b>Connection information</b>\n\n<b>Status</b>: {html.escape(status_str)} {status_dot}\n\n"
        )
        if not self.plugin_context.printer.is_closed_or_error():
            msg += render_emojis(
                f"<b>Connector</b>: {html.escape(connector_str)}\n"
                f"{connector_params_str}\n"
                f"<b>Profile</b>: {html.escape(profile_str)}"
            )

        # Build buttons
        keyboard = Keyboard(command_context.cmd)
        if self.plugin_context.printer.is_closed_or_error():
            keyboard.add_row(("{emo:online} Connect", "connect"), CLOSE_BUTTON)
        elif (
            self.plugin_context.printer.is_printing()
            or self.plugin_context.printer.is_pausing()
            or self.plugin_context.printer.is_paused()
            or self.plugin_context.printer.is_resuming()
            or self.plugin_context.printer.is_cancelling()
            or self.plugin_context.printer.is_finishing()
        ):
            msg += render_emojis("\n\n{emo:warning} You can't disconnect while printing.")
            keyboard.add_row(CLOSE_BUTTON)
        else:
            keyboard.add_row(("{emo:offline} Disconnect", "disconnect"), CLOSE_BUTTON)

        # Send message
        self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

    def _disconnect(self, command_context: CommandContext, params: list[str]) -> None:
        self.plugin_context.printer.disconnect()

        msg = render_emojis("{emo:check} Printer disconnected.")

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row((BACK_LABEL, ""))

        self.send_answer(command_context, msg, None, keyboard=keyboard)

    def _connect(self, command_context: CommandContext, params: list[str]) -> None:
        if params:
            if params[0] == "default":  # Default Connection
                connection_data = self._ask_default_connection_data(command_context, params[1:])
            elif params[0] == "serial" and self._is_serial_connection_available():  # Serial Connection
                connection_data = self._ask_serial_connection_data(command_context, params[1:])
            else:
                return

            # Connection data still needs more user input
            # (a message asking for the next parameter has already been sent)
            if connection_data is None:
                return

            self.send_answer(command_context, render_emojis("{emo:info} Connecting..."), None)

            parameters = connection_data["parameters"]
            self.plugin_context.printer.connect(
                # ty: ignore[invalid-argument-type] - wrong annotation in OctoPrint upstream
                connector=connection_data.get("connector"),
                parameters=parameters,
                # ty: ignore[invalid-argument-type] - wrong annotation in OctoPrint upstream
                profile=connection_data.get("profile"),
                port=parameters.get("port"),
                baudrate=parameters.get("baudrate"),
            )

            start_time = time.time()
            while time.time() - start_time < self.CONNECTION_TIMEOUT:
                if self.plugin_context.printer.is_operational() or self.plugin_context.printer.is_error():
                    break
                time.sleep(1)

            if self.plugin_context.printer.is_operational():
                msg = render_emojis("{emo:check} Connection established.")
            else:
                current_state = str(self.plugin_context.printer.get_state_string())
                msg = render_emojis(
                    "{emo:attention} Failed to start connection.\n"
                    f"Current state: <code>{html.escape(current_state)}</code>."
                )

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, ""))

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

        else:
            msg = render_emojis("{emo:question} How do you want to connect?")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row(("{emo:lamp} Use Default Connection", "connect_default"))
            if self._is_serial_connection_available():
                keyboard.add_row(("{emo:edit} Use Serial Connection", "connect_serial"))
            keyboard.add_row((BACK_LABEL, ""))

            self.send_answer(command_context, msg, None, keyboard=keyboard)

    def _ask_default_connection_data(self, command_context: CommandContext, params: list[str]) -> dict | None:
        all_profiles = self.plugin_context.printer_profiles.get_all()
        profile_ids = list(all_profiles.keys())

        preferred_connector = None
        preferred_parameters = {}
        if ConnectedPrinter is not None:
            preferred_connector = self.plugin_context.octoprint_settings.preferred_connector
            preferred_parameters = self.plugin_context.octoprint_settings.preferred_connection_parameters

        # Step 1: ask profile (skip if at most one available)
        if not params:
            if len(profile_ids) <= 1:
                return {
                    "connector": preferred_connector,
                    "parameters": preferred_parameters,
                    "profile": profile_ids[0] if profile_ids else None,
                }
            self._ask_choice(
                command_context,
                parent="connect",
                callback_prefix="connect_default",
                msg=self._build_connection_summary(preferred_connector, preferred_parameters)
                + render_emojis("{emo:question} Select the printer profile to use."),
                options=[(p["id"], p["name"]) for p in all_profiles.values()],
                item_emoji="profile",
            )
            return None

        menu_state = self.require_menu_state(command_context, ConMenuState)
        profile_id = self._chosen_option(menu_state, params[0])

        return {
            "connector": preferred_connector,
            "parameters": preferred_parameters,
            "profile": profile_id,
        }

    def _ask_serial_connection_data(self, command_context: CommandContext, params: list[str]) -> dict | None:
        if ConnectedPrinter is not None:
            serial_connector = ConnectedPrinter.find("serial")
            connection_options = serial_connector.connection_options() if serial_connector else {}

            ports = connection_options.get("port", [])
            baudrates = connection_options.get("baudrate", [])
        else:
            # OctoPrint < 2.0.0 backwards compatibility

            # nosemgrep (this is a fallback for older OctoPrint versions)
            connection_options = self.plugin_context.printer.get_connection_options()

            ports = connection_options["ports"]
            baudrates = connection_options["baudrates"]

        all_profiles = self.plugin_context.printer_profiles.get_all()
        profile_ids = list(all_profiles.keys())

        step = params[0] if params else ""
        choice = params[1] if len(params) > 1 else ""

        # Step 1: ask port
        if not step:
            self._ask_choice(
                command_context,
                parent="connect",
                callback_prefix="connect_serial_port",
                msg=render_emojis("{emo:question} Select the port to connect to."),
                options=[(p, p) for p in ports],
                item_emoji="port",
                with_auto=True,
            )
            return None

        menu_state = self.require_menu_state(command_context, ConMenuState)

        # Step 2: ask baudrate, either after the port was picked or coming back from the profile
        if step == "port" or (step == "baudrate" and not choice):
            port = self._chosen_option(menu_state, choice) if step == "port" else menu_state.port
            self._ask_choice(
                command_context,
                parent="connect_serial",
                callback_prefix="connect_serial_baudrate",
                msg=render_emojis("{emo:question} Select the baudrate to use."),
                options=[(b, b) for b in baudrates],
                item_emoji="speed",
                with_auto=True,
                port=port,
            )
            return None

        # Step 3: ask profile (skip if at most one available)
        if step == "baudrate":
            baudrate = self._chosen_option(menu_state, choice)

            if len(profile_ids) <= 1:
                return {
                    "connector": "serial",
                    "parameters": {"port": menu_state.port, "baudrate": baudrate},
                    "profile": profile_ids[0] if profile_ids else None,
                }
            self._ask_choice(
                command_context,
                parent="connect_serial_baudrate",
                callback_prefix="connect_serial_profile",
                msg=self._build_connection_summary("serial", {"port": menu_state.port, "baudrate": baudrate})
                + render_emojis("{emo:question} Select the printer profile to use."),
                options=[(p["id"], p["name"]) for p in all_profiles.values()],
                item_emoji="profile",
                port=menu_state.port,
                baudrate=baudrate,
            )
            return None

        if step == "profile":
            return {
                "connector": "serial",
                "parameters": {"port": menu_state.port, "baudrate": menu_state.baudrate},
                "profile": self._chosen_option(menu_state, choice),
            }

        return None

    def _ask_choice(
        self,
        command_context: CommandContext,
        parent: str,
        callback_prefix: str,
        msg: str,
        options: Sequence[tuple[str | int, str | int]],
        item_emoji: str,
        with_auto: bool = False,
        port: str | int | None = None,
        baudrate: str | int | None = None,
    ) -> None:
        """Ask the user to pick one value out of a list.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            parent (str): The parameter the back button runs the command with.
            callback_prefix (str): What every option runs the command with, its position appended to it.
            msg (str): The text shown above the options.
            options (Sequence[tuple]): The value and the label of every option.
            item_emoji (str): The name of the emoji shown on every option.
            with_auto (bool, optional): Offer an AUTO option on top of the list.
            port (str | int | None, optional): The port picked so far, or None for AUTO.
            baudrate (str | int | None, optional): The baudrate picked so far, or None for AUTO.
        """
        values = []
        buttons = []
        if with_auto:
            values.append(None)
            buttons.append(("{emo:lamp} AUTO", f"{callback_prefix}_0"))
        for value, label in options:
            values.append(value)
            buttons.append((f"{{emo:{item_emoji}}} {label}", f"{callback_prefix}_{len(values) - 1}"))

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_grid(buttons, buttons_per_row=3)
        keyboard.add_row((BACK_LABEL, parent))

        menu_state = ConMenuState(values, port=port, baudrate=baudrate)

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _chosen_option(self, menu_state: ConMenuState, choice: str) -> str | int | None:
        """Return the value behind the option the user picked.

        Args:
            menu_state (ConMenuState): The state of the menu the option was picked from.
            choice (str): The position the button carries.

        Returns:
            str | int | None: The value behind the option, or None if the user picked AUTO.

        Raises:
            StaleMenuError: If the menu offers no option at that position.
        """
        if not choice.isdigit() or int(choice) >= len(menu_state.options):
            raise StaleMenuError
        return menu_state.options[int(choice)]

    def _build_connection_summary(self, connector: str | None, parameters: dict | None) -> str:
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
                display = "AUTO" if value in (None, "") else str(value)
            lines.append(f"<b>{html.escape(label)}</b>: {html.escape(display)}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _is_serial_connection_available(self) -> bool:
        # Serial connection is always available on OctoPrint < 2.0.0 (no connectors at all)
        # or when the serial_connector plugin is installed and enabled on >= 2.0.0.
        return ConnectedPrinter is None or self.plugin_context.plugins.is_enabled("serial_connector")

    def _is_sensitive_param(self, key: str) -> bool:
        key_lower = str(key).lower()
        return any(keyword in key_lower for keyword in self.SENSITIVE_PARAM_KEYWORDS)
