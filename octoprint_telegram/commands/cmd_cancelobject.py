import html

from ..emoji import Emoji
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdCancelObject(BaseCommand):
    def execute(self, context: CommandContext):
        cancelobject_id = "cancelobject"

        if not self.main._plugin_manager.get_plugin(cancelobject_id, True):
            msg = f"{get_emoji('attention')} Please install <a href='https://plugins.octoprint.org/plugins/{cancelobject_id}/'>Cancelobject</a> plugin."
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                msg_id=context.msg_id_to_update,
            )
            return

        if context.parameter:
            params = context.parameter.split("_")

            id = params[0]
            self.main.send_octoprint_simpleapi_command(cancelobject_id, "cancel", dict(cancelled=id))

            msg = f"{get_emoji('check')} Command sent!"
            command_buttons = [[[f"{get_emoji('back')} Back", context.cmd]]]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )
        else:
            objlist = self.main.send_octoprint_simpleapi_command(cancelobject_id, "objlist").json().get("list", [])
            if objlist:
                msg = f"{get_emoji('question')} Which object do you want to cancel?"

                cancelled_objects = [obj["object"] for obj in objlist if obj.get("cancelled", False)]
                if cancelled_objects:
                    msg += "\n\nObjects already cancelled:\n"
                    msg += "\n".join(f"- <code>{html.escape(object_name)}</code>" for object_name in cancelled_objects)

                command_buttons = [
                    [[obj["object"], f"{context.cmd}_{obj['id']}"]]
                    for obj in objlist
                    if not obj.get("cancelled", False)
                ]
                command_buttons.append([[f"{get_emoji('cancel')} Close", "close"]])

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
            else:
                msg = f"{get_emoji('attention')} No objects found. Please make sure you've loaded the gcode."
                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    msg_id=context.msg_id_to_update,
                )
