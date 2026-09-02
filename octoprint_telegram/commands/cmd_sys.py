from __future__ import annotations

import html
import socket
from typing import ClassVar

import sarge
from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class SysMenuState(MenuState):
    """The system actions offered in the menu."""

    def __init__(self, action_identifiers: list[str]) -> None:
        """Set up the system actions offered in the menu.

        Args:
            action_identifiers (list[str]): The identifier of each action, in the order they are offered.
        """
        self.action_identifiers = action_identifiers


class CmdSys(BaseCommand):
    SERVER_COMMAND_LABELS: ClassVar[dict[str, str]] = {
        "serverRestartCommand": "Restart OctoPrint",
        "systemRestartCommand": "Restart system",
        "systemShutdownCommand": "Shutdown system",
    }

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Run one of the system commands OctoPrint offers.

        Possible callback queries, where {position} stands for the position of a system action in the list
        and {key} for one of OctoPrint's server command settings (serverRestartCommand, systemRestartCommand,
        systemShutdownCommand):

        - /sys -> list the system actions and the server commands
        - /sys_action_{position} -> run that system action, or ask for confirmation when that action asks for it
        - /sys_action_do_{position} -> run that system action
        - /sys_server_{key} -> ask for confirmation before running that server command
        - /sys_server_do_{key} -> run that server command
        """
        if command_context.parameter:
            params = command_context.parameter.split("_")

            if params[0] == "server":  # Server built-in commands
                confirmed = params[1] == "do"
                command_key = params[2] if confirmed else params[1]

                if command_key not in self.SERVER_COMMAND_LABELS:
                    return

                command_to_execute = self.plugin_context.octoprint_settings.server_command(command_key)
                if not command_to_execute:
                    return

                if not confirmed:  # Ask for confirmation
                    command_label = self.SERVER_COMMAND_LABELS[command_key]

                    msg = render_emojis(f"{{emo:question}} Execute System Command <b>{html.escape(command_label)}</b>?")

                    keyboard = Keyboard(command_context.cmd)
                    keyboard.add_row(("{emo:check} Execute", f"server_do_{command_key}"), (BACK_LABEL, ""))

                    self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

                else:  # Execute command
                    try:
                        process = sarge.run(command_to_execute, stderr=sarge.Capture(), shell=True, async_=False)

                        if process.returncode != 0:
                            returncode = str(process.returncode)
                            stderr_text = str(process.stderr.text)

                            self._logger.warning("Command failed with return code %s: %s", returncode, stderr_text)

                            msg = render_emojis(
                                f"{{emo:attention}} Command failed with return code <code>{html.escape(returncode)}</code>: <code>{html.escape(stderr_text)}</code>."
                            )
                        else:
                            msg = render_emojis("{emo:check} System Command executed.")
                    except Exception:
                        self._logger.exception("Caught an exception executing system command")
                        msg = render_emojis("{emo:attention} Command failed, please check log files.")

                    self.send_answer(command_context, msg, None, markup=Markup.HTML)

            else:  # Custom commands (system actions)
                confirmed = len(params) > 2 and params[1] == "do"
                action_index = params[2] if confirmed else (params[1] if len(params) > 1 else "")

                menu_state = self.require_menu_state(command_context, SysMenuState)

                action_identifier = (
                    menu_state.action_identifiers[int(action_index)]
                    if action_index.isdigit() and int(action_index) < len(menu_state.action_identifiers)
                    else None
                )

                actions = self.plugin_context.octoprint_settings.system_actions
                command = None
                for action in actions:
                    try:
                        if action["action"] == "divider":
                            continue

                        if f"{action['name']}-{action['action']}-{action['command']}" == action_identifier:
                            command = action
                            break
                    except Exception:
                        self._logger.exception("Caught an exception parsing system actions")

                if not command:
                    self.send_answer(
                        command_context,
                        render_emojis("{emo:attention} Sorry, I don't know this System Command."),
                        None,
                    )
                    return

                if "confirm" in command and not confirmed:  # Command requires confirmation, ask for it
                    msg = render_emojis(
                        f"{{emo:question}} Execute System Command <code>{html.escape(command['name'])}</code>?\n"
                        f"{{emo:info}} Confirmation message: <code>{html.escape(command['confirm'])}</code>"
                    )

                    keyboard = Keyboard(command_context.cmd)
                    keyboard.add_row(("{emo:check} Execute", f"action_do_{action_index}"), (BACK_LABEL, ""))

                    self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

                else:  # Execute command
                    async_ = command.get("async", False)

                    try:
                        process = sarge.run(
                            command["command"],
                            stderr=sarge.Capture(),
                            shell=True,
                            async_=async_,
                        )

                        msg = render_emojis(
                            f"{{emo:check}} System Command <code>{html.escape(command['name'])}</code> executed."
                        )

                        if not async_ and process.returncode != 0:
                            returncode = str(process.returncode)
                            stderr_text = str(process.stderr.text)

                            self._logger.warning("Command failed with return code %s: %s", returncode, stderr_text)

                            msg = render_emojis(
                                f"{{emo:attention}} Command <code>{html.escape(command['name'])}</code> failed with return code <code>{html.escape(returncode)}</code>: <code>{html.escape(stderr_text)}</code>."
                            )
                    except Exception:
                        self._logger.exception("Caught an exception executing system command")
                        msg = render_emojis("{emo:attention} Command failed, please check log files.")

                    self.send_answer(command_context, msg, None, markup=Markup.HTML)

        else:  # Display command buttons
            keyboard = Keyboard(command_context.cmd)
            action_identifiers = []

            for action in self.plugin_context.octoprint_settings.system_actions:
                try:
                    if action["action"] == "divider":
                        continue

                    action_identifiers.append(f"{action['name']}-{action['action']}-{action['command']}")
                    keyboard.add_row((f"{action['name']}", f"action_{len(action_identifiers) - 1}"))
                except Exception:
                    self._logger.exception("Caught an exception parsing system actions")

            server_commands_buttons = [
                (command_label, f"server_{command_key}")
                for command_key, command_label in self.SERVER_COMMAND_LABELS.items()
                if self.plugin_context.octoprint_settings.server_command(command_key)
            ]
            keyboard.add_grid(server_commands_buttons, buttons_per_row=2)

            if keyboard.rows:
                msg = render_emojis("{emo:question} Which System Command do you want to activate?")
            else:
                msg = render_emojis(
                    "{emo:warning} No System Commands found.\n"
                    "You can add custom commands from the OctoPrint web GUI using the "
                    "<a href='https://plugins.octoprint.org/plugins/systemcommandeditor/'>System Command Editor</a> plugin."
                )

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    host = self.plugin_context.octoprint_settings.online_check_host
                    port = self.plugin_context.octoprint_settings.online_check_port
                    s.connect((host, port))
                    server_ip = s.getsockname()[0]
                msg += render_emojis(f"\n\n{{emo:info}} IP: {server_ip}:{self.plugin_context.server_port}")
            except Exception:
                self._logger.exception("Caught an exception retrieving IP address")

            keyboard.add_row(CLOSE_BUTTON)

            self.send_answer(
                command_context, msg, SysMenuState(action_identifiers), markup=Markup.HTML, keyboard=keyboard
            )
