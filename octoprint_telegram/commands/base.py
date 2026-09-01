from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypeVar

from ..telegram import Buttons, Markup, MenuState, StaleMenuError

if TYPE_CHECKING:
    from ..core.context import PluginContext

T = TypeVar("T", bound=MenuState)


class CommandContext:
    def __init__(
        self,
        cmd: str,
        chat_id: str,
        from_id: str,
        parameter: str = "",
        msg_id_to_update: str = "",
        msg_id_to_reply_to: str = "",
        user: str = "",
    ) -> None:
        """Set up the details of a single command invocation.

        Args:
            cmd (str): The command being run.
            chat_id (str): The chat the command was sent from.
            from_id (str): The id of the user who sent the command.
            parameter (str, optional): The parameter the command was invoked with.
            msg_id_to_update (str, optional): The message to replace with the answer, instead of sending a new one.
            msg_id_to_reply_to (str, optional): The message the answer is a reply to.
            user (str, optional): The name of the user who sent the command.
        """
        self.cmd = cmd
        self.chat_id = chat_id
        self.from_id = from_id
        self.parameter = parameter
        self.msg_id_to_update = msg_id_to_update
        self.msg_id_to_reply_to = msg_id_to_reply_to
        self.user = user


class BaseCommand(ABC):
    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up a bot command.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("Commands")

    def __call__(
        self,
        cmd: str,
        chat_id: str,
        from_id: str,
        parameter: str = "",
        msg_id_to_update: str = "",
        msg_id_to_reply_to: str = "",
        user: str = "",
    ) -> None:
        """Run the command on a single invocation.

        Args:
            cmd (str): The command being run.
            chat_id (str): The chat the command was sent from.
            from_id (str): The id of the user who sent the command.
            parameter (str, optional): The parameter the command was invoked with.
            msg_id_to_update (str, optional): The message to replace with the answer, instead of sending a new one.
            msg_id_to_reply_to (str, optional): The message the answer is a reply to.
            user (str, optional): The name of the user who sent the command.
        """
        command_context = CommandContext(cmd, chat_id, from_id, parameter, msg_id_to_update, msg_id_to_reply_to, user)
        return self.execute(command_context)

    @abstractmethod
    def execute(self, command_context: CommandContext) -> None:
        """Run the command.

        Args:
            command_context (CommandContext): The details of a single command invocation.
        """

    def require_menu_state(self, command_context: CommandContext, menu_state_type: type[T]) -> T:
        """Return the state of the menu the command was invoked from.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            menu_state_type (type): The menu state class of the command.

        Returns:
            T: The state of the menu.

        Raises:
            StaleMenuError: If the message has no menu state of that class.
        """
        menu_state = self.plugin_context.menu_states.get_menu_state(
            command_context.chat_id, command_context.msg_id_to_update, menu_state_type
        )
        if menu_state is None:
            raise StaleMenuError
        return menu_state

    def update_menu(
        self,
        command_context: CommandContext,
        message: str,
        menu_state: MenuState | None,
        *,
        markup: Markup = Markup.OFF,
        buttons: Buttons | None = None,
        force_reply: bool = False,
    ) -> None:
        """Update the menu, replacing the message the command was invoked from.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            message (str): The text shown above the menu.
            menu_state (MenuState | None): The state the buttons refer to, or None when the message has no menu.
            markup (Markup, optional): The markup Telegram parses in the text.
            buttons (Buttons, optional): The inline keyboard shown under the message.
            force_reply (bool, optional): Show the reply interface in the chat.
        """
        message_id = self.plugin_context.sender.send_message(
            message,
            chat_id=command_context.chat_id,
            markup=markup,
            buttons=buttons,
            force_reply=force_reply,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
        if message_id:
            command_context.msg_id_to_update = message_id
            if menu_state is None:
                self.plugin_context.menu_states.discard_menu_state(command_context.chat_id, message_id)
            else:
                self.plugin_context.menu_states.set_menu_state(command_context.chat_id, message_id, menu_state)
