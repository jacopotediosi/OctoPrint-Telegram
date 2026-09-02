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

    def __init__(self, actions: list[tuple[str, str]]) -> None:
        """Set up the system actions offered in the menu.

        Args:
            actions (list[tuple[str, str]]): The source of each action, either "server" or "custom", then its
                identifier, in the order they are offered.
        """
        self.actions = actions


class CmdSys(BaseCommand):
    SERVER_COMMAND_LABELS: ClassVar[dict[str, str]] = {
        "serverRestartCommand": "Restart OctoPrint",
        "systemRestartCommand": "Restart system",
        "systemShutdownCommand": "Shutdown system",
    }

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Run one of the system commands OctoPrint offers.

        Possible callback queries, where {position} stands for the position of an action in the list:

        - /sys -> list the system actions and the server commands
        - /sys_{position} -> run the action at that position, or ask for confirmation when it asks for one
        - /sys_{position}_do -> run the action at that position
        """
        if command_context.parameter:
            position, _, confirmation = command_context.parameter.partition("_")
            confirmed = confirmation == "do"

            menu_state = self.require_menu_state(command_context, SysMenuState)
            action_source, action_identifier = self.require_menu_chosen_item(menu_state.actions, position)

            if action_source == "server":  # Server built-in commands
                command_to_execute = self.plugin_context.octoprint_settings.server_command(action_identifier)
                if not command_to_execute:
                    return

                if not confirmed:  # Ask for confirmation
                    command_label = self.SERVER_COMMAND_LABELS[action_identifier]

                    msg = render_emojis(f"{{emo:question}} Execute System Command <b>{html.escape(command_label)}</b>?")

                    keyboard = Keyboard(command_context.cmd)
                    keyboard.add_row(("{emo:check} Execute", f"{position}_do"), (BACK_LABEL, ""))

                    self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

                else:  # Execute command
                    try:
                        process = sarge.run(  # noqa: S604
                            command_to_execute, stderr=sarge.Capture(), shell=True, async_=False
                        )

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
                command = None
                for action in self.plugin_context.octoprint_settings.system_actions:
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
                    keyboard.add_row(("{emo:check} Execute", f"{position}_do"), (BACK_LABEL, ""))

                    self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

                else:  # Execute command
                    async_ = command.get("async", False)

                    try:
                        process = sarge.run(  # noqa: S604
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
            offered_actions = []

            for action in self.plugin_context.octoprint_settings.system_actions:
                try:
                    if action["action"] == "divider":
                        continue

                    offered_actions.append(("custom", f"{action['name']}-{action['action']}-{action['command']}"))
                    keyboard.add_row((f"{action['name']}", str(len(offered_actions) - 1)))
                except Exception:
                    self._logger.exception("Caught an exception parsing system actions")

            server_commands_buttons = []
            for command_key, command_label in self.SERVER_COMMAND_LABELS.items():
                if self.plugin_context.octoprint_settings.server_command(command_key):
                    offered_actions.append(("server", command_key))
                    server_commands_buttons.append((command_label, str(len(offered_actions) - 1)))
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

            self.send_answer(command_context, msg, SysMenuState(offered_actions), markup=Markup.HTML, keyboard=keyboard)
