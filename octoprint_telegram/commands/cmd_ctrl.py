from __future__ import annotations

import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CtrlMenuState(MenuState):
    """The printer controls offered in the menu."""

    def __init__(self, control_identifiers: list[str] | None = None, page: int = 0) -> None:
        """Set up the printer controls offered in the menu.

        Args:
            control_identifiers (list[str], optional): The identifier of each control, in the order they are offered.
            page (int, optional): The page of the controls being shown.
        """
        self.control_identifiers = control_identifiers or []
        self.page = page


class CmdCtrl(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Trigger one of the custom printer controls configured in OctoPrint.

        Possible callback queries, where {position} stands for the position of a control in the list:

        - /ctrl -> list the custom printer controls
        - /ctrl_prevpage -> show the previous page of the controls
        - /ctrl_nextpage -> show the next page of the controls
        - /ctrl_{position} -> trigger that control, or ask for confirmation when that control asks for it
        - /ctrl_execute_{position} -> trigger that control
        """
        if not self.plugin_context.printer.is_operational():
            self.send_answer(
                command_context,
                render_emojis("{emo:attention} Printer not connected. You can't trigger any control."),
                None,
            )
            return

        if command_context.parameter:
            action, _, argument = command_context.parameter.partition("_")

            if action in ("prevpage", "nextpage"):
                menu_state = self.require_menu_state(command_context, CtrlMenuState)
                menu_state.page += -1 if action == "prevpage" else 1
                self._list_controls(command_context, menu_state)
                return

            control_index = argument if action == "execute" else action

            menu_state = self.require_menu_state(command_context, CtrlMenuState)

            control_identifier = self.require_menu_chosen_item(menu_state.control_identifiers, control_index)

            controls = self._get_controls()
            control = next((c for c in controls if c["identifier"] == control_identifier), None)

            if not control:
                self.send_answer(command_context, render_emojis("{emo:attention} Control Command not found."), None)
                return

            if "confirm" in control and action != "execute":  # Control requires confirmation, ask for it
                msg = render_emojis(
                    f"{{emo:question}} Execute control command <code>{html.escape(control['name'])}</code>?\n"
                    f"{{emo:info}} Confirmation message: <code>{html.escape(control['confirm'])}</code>"
                )

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row(("{emo:check} Execute", f"execute_{control_index}"), (BACK_LABEL, ""))

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
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

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_row((BACK_LABEL, ""))

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)

        else:  # Display all available commands
            self._list_controls(command_context, CtrlMenuState())

    def _list_controls(self, command_context: CommandContext, menu_state: CtrlMenuState) -> None:
        """List the custom printer controls."""
        message = render_emojis("{emo:question} Which Printer Control do you want to trigger?")

        try:
            controls = self._get_controls()
        except Exception:
            self._logger.exception("Caught an exception getting printer control list")
            controls = []

        keyboard = Keyboard(command_context.cmd)
        menu_state.control_identifiers, menu_state.page, _ = keyboard.add_entries_page(
            [(control["identifier"], control["name"], "") for control in controls], 1, menu_state.page
        )

        if not controls:
            message += render_emojis(
                "\n\n{emo:warning} No Printer Controls found.\n"
                "You can add custom controls from the OctoPrint web GUI using the "
                "<a href='http://plugins.octoprint.org/plugins/customControl/'>Custom Control Editor</a> plugin."
            )

        keyboard.add_row(CLOSE_BUTTON)

        self.send_answer(command_context, message, menu_state, markup=Markup.HTML, keyboard=keyboard)

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
                            "identifier": f"{key_name}-{command_str}",
                        }
                    )

                    if "confirm" in key:
                        control["confirm"] = key["confirm"]

                    controls.append(control)
            except Exception:
                self._logger.exception("Caught an exception processing control key")

        return controls
