import hashlib
import html
import socket

import sarge

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdSys(BaseCommand):
    def execute(self, context: CommandContext):
        if context.parameter:
            params = context.parameter.split("_")

            if params[0] == "sys":  # Server built-in commands
                command_mapping = {
                    "serverRestartCommand": "Restart OctoPrint",
                    "systemRestartCommand": "Restart system",
                    "systemShutdownCommand": "Shutdown system",
                }

                if params[1] != "do":  # Ask for confirmation
                    if params[1] not in command_mapping:
                        return

                    msg = render_emojis(
                        f"{{emo:question}} Execute System Command <b>{html.escape(command_mapping[params[1]])}</b>?"
                    )

                    command_buttons = [
                        [
                            [
                                render_emojis("{emo:check} Execute"),
                                f"{context.cmd}_sys_do_{params[1]}",
                            ],
                            [
                                render_emojis("{emo:back} Back"),
                                context.cmd,
                            ],
                        ]
                    ]

                    self.main.send_msg(
                        msg,
                        chatID=context.chat_id,
                        markup="HTML",
                        responses=command_buttons,
                        msg_id=context.msg_id_to_update,
                    )

                else:  # Execute command
                    if params[2] not in command_mapping:
                        return

                    try:
                        command_to_execute = self.main._settings.global_get(["server", "commands", params[2]])
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

                    self.main.send_msg(
                        msg,
                        chatID=context.chat_id,
                        markup="HTML",
                        msg_id=context.msg_id_to_update,
                    )

            else:  # Custom commands (system actions)
                action_hash = params[1] if params[0] == "do" else params[0]

                actions = self.main._settings.global_get(["system", "actions"])
                command = None
                for action in actions:
                    try:
                        if action["action"] == "divider":
                            continue

                        action_identifier = f"{action['name']}-{action['action']}-{action['command']}"
                        if self.hash_parameter(action_identifier) == action_hash:
                            command = action
                            break
                    except Exception:
                        self._logger.exception("Caught an exception parsing system actions")

                if not command:
                    self.main.send_msg(
                        render_emojis("{emo:attention} Sorry, I don't know this System Command."),
                        chatID=context.chat_id,
                        msg_id=context.msg_id_to_update,
                    )
                    return

                if "confirm" in command and params[0] != "do":  # Command requires confirmation, ask for it
                    msg = render_emojis(
                        f"{{emo:question}} Execute System Command <code>{html.escape(command['name'])}</code>?\n"
                        f"{{emo:info}} Confirmation message: <code>{html.escape(command['confirm'])}</code>"
                    )

                    command_buttons = [
                        [
                            [
                                render_emojis("{emo:check} Execute"),
                                f"{context.cmd}_do_{action_hash}",
                            ],
                            [
                                render_emojis("{emo:back} Back"),
                                context.cmd,
                            ],
                        ]
                    ]

                    self.main.send_msg(
                        msg,
                        chatID=context.chat_id,
                        markup="HTML",
                        responses=command_buttons,
                        msg_id=context.msg_id_to_update,
                    )

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

                    self.main.send_msg(
                        msg,
                        chatID=context.chat_id,
                        markup="HTML",
                        msg_id=context.msg_id_to_update,
                    )

        else:  # Display command buttons
            command_buttons = []

            for action in self.main._settings.global_get(["system", "actions"]):
                try:
                    if action["action"] == "divider":
                        continue

                    action_identifier = f"{action['name']}-{action['action']}-{action['command']}"
                    command_buttons.append(
                        [[f"{action['name']}", f"{context.cmd}_{self.hash_parameter(action_identifier)}"]]
                    )
                except Exception:
                    self._logger.exception("Caught an exception parsing system actions")

            server_commands_buttons = []
            server_commands_map = {
                "serverRestartCommand": [
                    "Restart OctoPrint",
                    f"{context.cmd}_sys_serverRestartCommand",
                ],
                "systemRestartCommand": ["Restart system", f"{context.cmd}_sys_systemRestartCommand"],
                "systemShutdownCommand": [
                    "Shutdown system",
                    f"{context.cmd}_sys_systemShutdownCommand",
                ],
            }
            for command_key, command_button in server_commands_map.items():
                command_text = self.main._settings.global_get(["server", "commands", command_key])
                if command_text:
                    server_commands_buttons.append(command_button)
            for i in range(0, len(server_commands_buttons), 2):
                command_buttons.append(server_commands_buttons[i : i + 2])

            if command_buttons:
                msg = render_emojis("{emo:question} Which System Command do you want to activate?")
            else:
                msg = render_emojis(
                    "{emo:warning} No System Commands found.\n"
                    "You can add custom commands from the OctoPrint web GUI using the "
                    "<a href='https://plugins.octoprint.org/plugins/systemcommandeditor/'>System Command Editor</a> plugin."
                )

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    host = self.main._settings.global_get(["server", "onlineCheck", "host"])
                    port = self.main._settings.global_get(["server", "onlineCheck", "port"])
                    s.connect((host, port))
                    server_ip = s.getsockname()[0]
                msg += render_emojis(f"\n\n{{emo:info}} IP: {server_ip}:{self.main.port}")
            except Exception:
                self._logger.exception("Caught an exception retrieving IP address")

            command_buttons.append([[render_emojis("{emo:cancel} Close"), "close"]])

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def hash_parameter(self, text):
        return hashlib.md5(text.encode()).hexdigest()
