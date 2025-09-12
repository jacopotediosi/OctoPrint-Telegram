import hashlib
import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdCtrl(BaseCommand):
    def execute(self, context: CommandContext):
        if not self.main._printer.is_operational():
            self.main.send_msg(
                f"{get_emoji('attention')} Printer not connected. You can't trigger any control.",
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        if context.parameter:
            params = context.parameter.split("_")

            control_hash = params[1] if params[0] == "do" else params[0]

            controls = self.get_controls()
            control = next((c for c in controls if c["hash"] == control_hash), None)

            if not control:
                self.main.send_msg(
                    f"{get_emoji('attention')} Control Command not found.",
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
                return

            if "confirm" in control and params[0] != "do":  # Control requires confirmation, ask for it
                msg = (
                    f"{get_emoji('question')} Execute control command <code>{html.escape(control['name'])}</code>?\n"
                    f"{get_emoji('info')} Confirmation message: <code>{html.escape(control['confirm'])}</code>"
                )

                command_buttons = [
                    [
                        [
                            f"{get_emoji('check')} Execute",
                            f"{context.cmd}_do_{control_hash}",
                        ],
                        [
                            f"{get_emoji('back')} Back",
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
            else:  # Execute Control
                try:
                    if control.get("type") == "script":
                        self.main._printer.script(control["command"])
                    elif control.get("type") == "commands":
                        for command in control["command"]:
                            self.main._printer.commands(command)

                    msg = f"{get_emoji('check')} Control Command <code>{html.escape(control['name'])}</code> executed."
                except Exception:
                    self._logger.exception("Caught an exception executing a Control Command")
                    msg = (
                        f"{get_emoji('attention')} Control Command <code>{html.escape(control['name'])}</code> failed."
                    )

                command_buttons = [
                    [
                        [
                            f"{get_emoji('back')} Back",
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

        else:  # Display all available commands
            message = f"{get_emoji('question')} Which Printer Control do you want to trigger?"

            try:
                command_buttons = [
                    [[control["name"], f"{context.cmd}_{control['hash']}"]] for control in self.get_controls()
                ]
            except Exception:
                self._logger.exception("Caught an exception getting printer control list")
                command_buttons = []

            if not command_buttons:
                message += (
                    f"\n\n{get_emoji('warning')} No Printer Controls found.\n"
                    "You can add custom controls from the OctoPrint web GUI using the "
                    "<a href='http://plugins.octoprint.org/plugins/customControl/'>Custom Control Editor</a> plugin."
                )

            command_buttons.append([[f"{get_emoji('cancel')} Close", "close"]])

            self.main.send_msg(
                message,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def get_controls(self, tree=None, container=""):
        controls = []

        if tree is None:
            tree = self.main._settings.global_get(["controls"])

        for key in tree:
            try:
                if not isinstance(key, dict):
                    continue

                key_name = f"{container}/{key['name']}" if container else key["name"]

                if "children" in key:
                    controls.extend(self.get_controls(key["children"], key_name))
                else:
                    if key.get("input"):
                        self._logger.warning("Skipping %s Control because it requires input.", key_name)
                        continue

                    control = {}

                    if "script" in key:
                        control["type"] = "script"

                        command = key["script"]
                    elif "command" in key or "commands" in key:
                        control["type"] = "commands"

                        if "command" in key:
                            command = key["command"]
                        else:
                            command = key["commands"]

                        if not isinstance(command, list):
                            command = [command]
                    else:
                        self._logger.warning("Skipping %s Control because it's not a script nor a command.", key_name)
                        continue

                    command_str = ",".join(command) if isinstance(command, list) else str(command)
                    control.update(
                        {
                            "name": key_name,
                            "command": command,
                            "hash": self.hash_control(f"{key_name}-{command_str}"),
                        }
                    )

                    if "confirm" in key:
                        control["confirm"] = key["confirm"]

                    controls.append(control)
            except Exception:
                self._logger.exception("Caught an exception processing control key")

        return controls

    def hash_control(self, control_identifier):
        return hashlib.md5(control_identifier.encode()).hexdigest()
