import html

from typing_extensions import override

from ..emoji import Emoji
from ..telegram import Markup
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class CmdCancelObject(BaseCommand):
    @override
    def execute(self, command_context: CommandContext) -> None:
        cancelobject_id = "cancelobject"

        if not self.plugin_context.plugins.is_enabled(cancelobject_id):
            msg = render_emojis(
                f"{{emo:attention}} Please install <a href='https://plugins.octoprint.org/plugins/{cancelobject_id}/'>Cancelobject</a> plugin."
            )
            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                message_id=command_context.msg_id_to_update,
            )
            return

        if command_context.parameter:
            params = command_context.parameter.split("_")

            id = params[0]
            self.plugin_context.api.send_simpleapi_command(cancelobject_id, "cancel", {"cancelled": id})

            msg = render_emojis("{emo:check} Command sent!")
            command_buttons = [[(render_emojis("{emo:back} Back"), command_context.cmd)]]

            self.plugin_context.sender.send_message(
                msg,
                chat_id=command_context.chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=command_context.msg_id_to_update,
            )
        else:
            objlist = self.plugin_context.api.send_simpleapi_command(cancelobject_id, "objlist").json().get("list", [])
            if objlist:
                msg = render_emojis("{emo:question} Which object do you want to cancel?")

                cancelled_objects = [obj["object"] for obj in objlist if obj.get("cancelled", False)]
                if cancelled_objects:
                    msg += "\n\nObjects already cancelled:\n"
                    msg += "\n".join(f"- <code>{html.escape(object_name)}</code>" for object_name in cancelled_objects)

                command_buttons = [
                    [(obj["object"], f"{command_context.cmd}_{obj['id']}")]
                    for obj in objlist
                    if not obj.get("cancelled", False)
                ]
                command_buttons.append([(render_emojis("{emo:cancel} Close"), "close")])

                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    buttons=command_buttons,
                    message_id=command_context.msg_id_to_update,
                )
            else:
                msg = render_emojis(
                    "{emo:attention} No objects found. Please make sure you've selected for printing the gcode."
                )
                self.plugin_context.sender.send_message(
                    msg,
                    chat_id=command_context.chat_id,
                    markup=Markup.HTML,
                    message_id=command_context.msg_id_to_update,
                )
