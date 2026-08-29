from __future__ import annotations

import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup, callbacks
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdCtrl(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        if not self.plugin_context.printer.is_operational():
            self.plugin_context.sender.send_message(
                render_emojis("{emo:attention} Printer not connected. You can't trigger any control."),
                chat_id=command_context.chat_id,
                message_id=command_context.msg_id_to_update,
            )
            return

        if command_context.parameter:
            params = command_context.parameter.split("_")

            control_hash = params[1] if params[0] == "do" else params[0]

            controls = self._get_controls()
            control = next((c for c in controls if c["hash"] == control_hash), None)

            if not control:
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:attention} Control Command not found."),
                    chat_id=command_context.chat_id,
                    message_id=command_context.msg_id_to_update,
                )
                return

            if "confirm" in control and params[0] != "do":  # Control requires confirmation, ask for it
                msg = render_emojis(
                    f"{{emo:question}} Execute control command <code>{html.escape(control['name'])}</code>?\n"
                    f"{{emo:info}} Confirmation message: <code>{html.escape(control['confirm'])}</code>"
                )

                command_buttons = [
                    [
                        (
                            render_emojis("{emo:check} Execute"),
                            f"{command_context.cmd}_do_{control_hash}",
                        ),
                        (
                            render_emojis("{emo:back} Back"),
                            command_context.cmd,
                        ),
                    ]
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
            else:  # Execute Control
                try:
                    if control.get("type") == "script":
                        self.plugin_context.printer.script(control["command"])
                    elif control.get("type") == "commands":
                        for command in control["command"]:
                            self.plugin_context.printer.commands(command)

                    msg = render_emojis(
                        f"{{emo:check}} Control Command <code>{html.escape(control['name'])}</code> executed."
                    )
                except Exception:
                    self._logger.exception("Caught an exception executing a Control Command")
                    msg = render_emojis(
                        f"{{emo:attention}} Control Command <code>{html.escape(control['name'])}</code> failed."
                    )

                command_buttons = [
                    [
                        (
                            render_emojis("{emo:back} Back"),
                            command_context.cmd,
                        ),
                    ]
                ]

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )

        else:  # Display all available commands
            message = render_emojis("{emo:question} Which Printer Control do you want to trigger?")

            try:
                command_buttons = [
                    [(control["name"], f"{command_context.cmd}_{control['hash']}")] for control in self._get_controls()
                ]
            except Exception:
                self._logger.exception("Caught an exception getting printer control list")
                command_buttons = []

            if not command_buttons:
                message += render_emojis(
                    "\n\n{emo:warning} No Printer Controls found.\n"
                    "You can add custom controls from the OctoPrint web GUI using the "
                    "<a href='http://plugins.octoprint.org/plugins/customControl/'>Custom Control Editor</a> plugin."
                )

            command_buttons.append([(render_emojis("{emo:cancel} Close"), "close")])

            self.plugin_context.sender.send_message(
                message,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=command_context.msg_id_to_update,
            )

    def _get_controls(self, tree: list | None = None, container: str = "") -> list[dict]:
        """Flatten the custom controls the user defined in OctoPrint.

        Args:
            tree (list, optional): The controls to walk. Defaults to the ones OctoPrint has configured.
            container (str, optional): The path the walked controls are nested under.

        Returns:
            list[dict]: The flattened controls.
        """
        controls = []

        if tree is None:
            tree = self.plugin_context.octoprint_settings.controls

        for key in tree:
            try:
                if not isinstance(key, dict):
                    continue

                key_name = f"{container}/{key['name']}" if container else key["name"]

                if "children" in key:
                    controls.extend(self._get_controls(key["children"], key_name))
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
                            "hash": self._hash_control(f"{key_name}-{command_str}"),
                        }
                    )

                    if "confirm" in key:
                        control["confirm"] = key["confirm"]

                    controls.append(control)
            except Exception:
                self._logger.exception("Caught an exception processing control key")

        return controls

    def _hash_control(self, control_identifier: str) -> str:
        return callbacks.hash_value(control_identifier)
