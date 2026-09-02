from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

from ..telegram import AwaitedReply, Buttons, Markup, MenuState, StaleMenuError

if TYPE_CHECKING:
    from ..core.context import PluginContext

T = TypeVar("T", bound=MenuState)


@dataclass
class CommandContext:
    """Describes a single command invocation: what was invoked, by whom, and where the answer goes."""

    cmd: str
    """The command being run."""

    chat_id: str
    """The chat the command was sent from."""

    from_id: str
    """The id of the user who sent the command."""

    parameter: str = ""
    """The parameter the command was invoked with."""

    msg_id_to_update: str = ""
    """The message to replace with the answer, instead of sending a new one."""

    msg_id_to_reply_to: str = ""
    """The message the answer is a reply to."""

    telegram_user: dict = field(default_factory=dict)
    """The Telegram user who sent the command."""

    @property
    def user(self) -> str:
        """The name of the user who sent the command."""
        username = self.telegram_user.get("username")

        first_name = self.telegram_user.get("first_name")
        last_name = self.telegram_user.get("last_name")
        fullname = " ".join(part for part in (first_name, last_name) if part).strip()

        parts = []

        if username:
            parts.append(f"@{username}")
        if fullname:
            parts.append(fullname)

        return "Telegram - " + (" - ".join(parts) if parts else "UNKNOWN")


class BaseCommand(ABC):
    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up a bot command.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("Commands")

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
        reply_parameter_prefix: str = "",
        delete_answer_message: bool = False,
    ) -> None:
        """Update the menu, replacing the message the command was invoked from.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            message (str): The text shown above the menu.
            menu_state (MenuState | None): The state the buttons refer to, or None when the message has no menu.
            markup (Markup, optional): The markup Telegram parses in the text.
            buttons (Buttons, optional): The inline keyboard shown under the message.
            force_reply (bool, optional): Ask the user to answer the message with the parameter of the command.
            reply_parameter_prefix (str, optional): What the answer is appended to, to build that parameter.
            delete_answer_message (bool, optional): Remove the message carrying the answer from the chat, once the
                command has run.
        """
        msg_id_to_update = command_context.msg_id_to_update

        message_id = self.plugin_context.sender.send_message(
            message,
            chat_id=command_context.chat_id,
            markup=markup,
            buttons=buttons,
            force_reply=force_reply,
            message_id=msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
        if message_id:
            command_context.msg_id_to_update = message_id
            awaited_reply = (
                AwaitedReply(command_context.cmd, reply_parameter_prefix, msg_id_to_update, delete_answer_message)
                if force_reply
                else None
            )
            if menu_state is None and awaited_reply is None:
                self.plugin_context.menu_states.discard_menu_state(command_context.chat_id, message_id)
            else:
                self.plugin_context.menu_states.set_menu_state(
                    command_context.chat_id, message_id, menu_state, awaited_reply
                )
