from __future__ import annotations

import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CancelObjectMenuState(MenuState):
    """The objects offered in the menu."""

    def __init__(self, object_ids: list[str]) -> None:
        """Set up the objects offered in the menu.

        Args:
            object_ids (list[str]): The id of each object, in the order they are offered.
        """
        self.object_ids = object_ids


class CmdCancelObject(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Cancel one of the objects of the running print.

        Possible callback queries, where {position} stands for the position of an object in the list:

        - /cancelobject -> list the objects that can still be cancelled
        - /cancelobject_{position} -> cancel the object at that position
        """
        cancelobject_id = "cancelobject"

        if not self.plugin_context.plugins.is_enabled(cancelobject_id):
            msg = render_emojis(
                f"{{emo:attention}} Please install <a href='https://plugins.octoprint.org/plugins/{cancelobject_id}/'>Cancelobject</a> plugin."
            )
            self.send_answer(command_context, msg, None, markup=Markup.HTML)
            return

        if command_context.parameter:
            menu_state = self.require_menu_state(command_context, CancelObjectMenuState)
            object_id = self.require_menu_chosen_item(menu_state.object_ids, command_context.parameter)

            self.plugin_context.api.send_simpleapi_command(cancelobject_id, "cancel", {"cancelled": object_id})

            msg = render_emojis("{emo:check} Command sent!")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, ""))

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
        else:
            printed_objects = (
                self.plugin_context.api.send_simpleapi_command(cancelobject_id, "objlist").json().get("list", [])
            )
            if printed_objects:
                msg = render_emojis("{emo:question} Which object do you want to cancel?")

                cancelled_objects = [
                    printed_object["object"]
                    for printed_object in printed_objects
                    if printed_object.get("cancelled", False)
                ]
                if cancelled_objects:
                    msg += "\n\nObjects already cancelled:\n"
                    msg += "\n".join(f"- <code>{html.escape(object_name)}</code>" for object_name in cancelled_objects)

                cancellable_objects = [
                    printed_object for printed_object in printed_objects if not printed_object.get("cancelled", False)
                ]

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_grid(
                    [
                        (printed_object["object"], str(object_position))
                        for object_position, printed_object in enumerate(cancellable_objects)
                    ],
                    buttons_per_row=1,
                )
                keyboard.add_row(CLOSE_BUTTON)

                menu_state = CancelObjectMenuState(
                    [str(printed_object["id"]) for printed_object in cancellable_objects]
                )

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
            else:
                msg = render_emojis(
                    "{emo:attention} No objects found. Please make sure you've selected for printing the gcode."
                )
                self.send_answer(command_context, msg, None, markup=Markup.HTML)
