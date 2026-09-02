import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdCancelObject(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        """Cancel one of the objects of the running print.

        Possible callback queries, where {object_id} stands for the id the Cancelobject plugin gave an object:

        - /cancelobject -> list the objects that can still be cancelled
        - /cancelobject_{object_id} -> cancel that object
        """
        cancelobject_id = "cancelobject"

        if not self.plugin_context.plugins.is_enabled(cancelobject_id):
            msg = render_emojis(
                f"{{emo:attention}} Please install <a href='https://plugins.octoprint.org/plugins/{cancelobject_id}/'>Cancelobject</a> plugin."
            )
            self.send_answer(command_context, msg, None, markup=Markup.HTML)
            return

        if command_context.parameter:
            params = command_context.parameter.split("_")

            object_id = params[0]
            self.plugin_context.api.send_simpleapi_command(cancelobject_id, "cancel", {"cancelled": object_id})

            msg = render_emojis("{emo:check} Command sent!")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, ""))

            self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
        else:
            objlist = self.plugin_context.api.send_simpleapi_command(cancelobject_id, "objlist").json().get("list", [])
            if objlist:
                msg = render_emojis("{emo:question} Which object do you want to cancel?")

                cancelled_objects = [obj["object"] for obj in objlist if obj.get("cancelled", False)]
                if cancelled_objects:
                    msg += "\n\nObjects already cancelled:\n"
                    msg += "\n".join(f"- <code>{html.escape(object_name)}</code>" for object_name in cancelled_objects)

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_grid(
                    [(obj["object"], str(obj["id"])) for obj in objlist if not obj.get("cancelled", False)],
                    buttons_per_row=1,
                )
                keyboard.add_row(CLOSE_BUTTON)

                self.send_answer(command_context, msg, None, markup=Markup.HTML, keyboard=keyboard)
            else:
                msg = render_emojis(
                    "{emo:attention} No objects found. Please make sure you've selected for printing the gcode."
                )
                self.send_answer(command_context, msg, None, markup=Markup.HTML)
