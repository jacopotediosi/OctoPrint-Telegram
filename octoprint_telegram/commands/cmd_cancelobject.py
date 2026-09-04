from __future__ import annotations

import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis

CANCELOBJECT_PLUGIN_ID = "cancelobject"


class CancelObjectMenuState(MenuState):
    """The objects offered in the menu."""

    def __init__(self, object_ids: list[str] | None = None, page: int = 0) -> None:
        """Set up the objects offered in the menu.

        Args:
            object_ids (list[str], optional): The id of each object, in the order they are offered.
            page (int, optional): The page of the objects being shown.
        """
        self.object_ids = object_ids or []
        self.page = page


class CmdCancelObject(BaseCommand):
    MAX_LISTED_CANCELLED_OBJECTS = 10

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Cancel one of the objects of the running print.

        Possible callback queries, where {position} stands for the position of an object in the list:

        - /cancelobject -> list the objects that can still be cancelled
        - /cancelobject_prevpage -> show the previous page of the objects
        - /cancelobject_nextpage -> show the next page of the objects
        - /cancelobject_{position} -> cancel the object at that position
        """
        if not self.plugin_context.plugins.is_enabled(CANCELOBJECT_PLUGIN_ID):
            msg = render_emojis(
                f"{{emo:attention}} Please install <a href='https://plugins.octoprint.org/plugins/{CANCELOBJECT_PLUGIN_ID}/'>Cancelobject</a> plugin."
            )
            self.send_answer(command_context, msg, None, markup=Markup.HTML)
            return

        if command_context.parameter:
            if command_context.parameter in ("prevpage", "nextpage"):
                menu_state = self.require_menu_state(command_context, CancelObjectMenuState)
                menu_state.page += -1 if command_context.parameter == "prevpage" else 1
                self._list_objects(command_context, menu_state)
                return

            menu_state = self.require_menu_state(command_context, CancelObjectMenuState)
            object_id = self.require_menu_chosen_item(menu_state.object_ids, command_context.parameter)

            self.plugin_context.api.send_simpleapi_command(CANCELOBJECT_PLUGIN_ID, "cancel", {"cancelled": object_id})

            msg = render_emojis("{emo:check} Command sent!")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, ""))

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
        else:
            self._list_objects(command_context, CancelObjectMenuState())

    def _list_objects(self, command_context: CommandContext, menu_state: CancelObjectMenuState) -> None:
        """List the objects that can still be cancelled."""
        printed_objects = (
            self.plugin_context.api.send_simpleapi_command(CANCELOBJECT_PLUGIN_ID, "objlist").json().get("list", [])
        )
        if printed_objects:
            msg = render_emojis("{emo:question} Which object do you want to cancel?")

            cancelled_objects = [
                printed_object["object"] for printed_object in printed_objects if printed_object.get("cancelled", False)
            ]
            if len(cancelled_objects) > self.MAX_LISTED_CANCELLED_OBJECTS:
                msg += f"\n\n{len(cancelled_objects)} objects already cancelled."
            elif cancelled_objects:
                msg += "\n\nObjects already cancelled:\n"
                msg += "\n".join(f"- <code>{html.escape(object_name)}</code>" for object_name in cancelled_objects)

            cancellable_objects = [
                printed_object for printed_object in printed_objects if not printed_object.get("cancelled", False)
            ]

            keyboard = Keyboard(command_context.cmd)
            menu_state.object_ids, menu_state.page, _ = keyboard.add_entries_page(
                [(str(printed_object["id"]), printed_object["object"], "") for printed_object in cancellable_objects],
                menu_state.page,
                1,
            )
            keyboard.add_row(CLOSE_BUTTON)

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
        else:
            msg = render_emojis(
                "{emo:attention} No objects found. Please make sure you've selected for printing the gcode."
            )
            self.send_answer(command_context, msg, None, markup=Markup.HTML)
