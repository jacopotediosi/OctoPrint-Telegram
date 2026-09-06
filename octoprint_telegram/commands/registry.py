from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .cmd_abort import CmdAbort
from .cmd_cancelobject import CmdCancelObject
from .cmd_close import CmdClose
from .cmd_con import CmdCon
from .cmd_ctrl import CmdCtrl
from .cmd_dontshutup import CmdDontShutup
from .cmd_filament import CmdFilament
from .cmd_files import CmdFiles
from .cmd_gcode import CmdGcode
from .cmd_gif import CmdGif
from .cmd_help import CmdHelp
from .cmd_home import CmdHome
from .cmd_photo import CmdPhoto
from .cmd_power import CmdPower
from .cmd_print import CmdPrint
from .cmd_settings import CmdSettings
from .cmd_shutup import CmdShutup
from .cmd_start import CmdStart
from .cmd_status import CmdStatus
from .cmd_supergif import CmdSuperGif
from .cmd_sys import CmdSys
from .cmd_togglepause import CmdTogglePause
from .cmd_tune import CmdTune
from .cmd_upload import CmdUpload
from .cmd_user import CmdUser

if TYPE_CHECKING:
    from .base import BaseCommand


@dataclass(frozen=True)
class CommandDefinition:
    """Describes a bot command: how users invoke it and how it is presented to them."""

    name: str
    """The command as typed by the user, usually starting with /."""

    implementation: type[BaseCommand]
    """The class implementing the command."""

    description: str
    """Human-readable description shown to users."""

    takes_parameter: bool = False
    """Whether the command takes a parameter."""

    available_to_everyone: bool = False
    """Whether anyone may run the command, with no permission to configure."""

    def __post_init__(self) -> None:
        """Check the validity of the declared command.

        Raises:
            ValueError: If the command is not valid.
        """
        if not self.description.strip():
            raise ValueError(f"Command {self.name} has no description")

    @property
    def shown_to_users(self) -> bool:
        """Whether the command is offered in the Telegram command list and in /help."""
        return self.name.startswith("/")


# Declaration order is the order shown to users.
#
# Each time you add/remove a command or notification, please remember also
# to increment the settings version number in `get_settings_version`.

COMMAND_DEFINITIONS: tuple[CommandDefinition, ...] = (
    CommandDefinition("/status", CmdStatus, "Show current status"),
    CommandDefinition("/togglepause", CmdTogglePause, "Pause or resume the current print"),
    CommandDefinition("/home", CmdHome, "Home the printer's print head"),
    CommandDefinition(
        "/files",
        CmdFiles,
        "Browse and manage files, select for printing, and slice models",
        takes_parameter=True,
    ),
    CommandDefinition("/print", CmdPrint, "Print the file selected for printing", takes_parameter=True),
    CommandDefinition("/tune", CmdTune, "Adjust feed rate, flow rate, and temperatures", takes_parameter=True),
    CommandDefinition("/ctrl", CmdCtrl, "Trigger custom OctoPrint controls", takes_parameter=True),
    CommandDefinition("/con", CmdCon, "Connect or disconnect the printer", takes_parameter=True),
    CommandDefinition("/sys", CmdSys, "Run OctoPrint system commands", takes_parameter=True),
    CommandDefinition("/abort", CmdAbort, "Abort current print (confirmation required)", takes_parameter=True),
    CommandDefinition(
        "/cancelobject",
        CmdCancelObject,
        "Cancel an object (Cancelobject plugin required)",
        takes_parameter=True,
    ),
    CommandDefinition("/power", CmdPower, "Monitor and control power switches", takes_parameter=True),
    CommandDefinition("/settings", CmdSettings, "Show and change notification settings", takes_parameter=True),
    CommandDefinition("/upload", CmdUpload, "Upload a file to OctoPrint library"),
    CommandDefinition("/filament", CmdFilament, "Manage filament spools", takes_parameter=True),
    CommandDefinition("/user", CmdUser, "Get information about chat, user and permissions"),
    CommandDefinition(
        "/gcode",
        CmdGcode,
        "Send G-code commands to the printer",
        takes_parameter=True,
    ),
    CommandDefinition("/gif", CmdGif, "Show GIFs from the webcams"),
    CommandDefinition("/supergif", CmdSuperGif, "Show longer GIFs from the webcams"),
    CommandDefinition("/photo", CmdPhoto, "Show photos from the webcams"),
    CommandDefinition("/shutup", CmdShutup, "Disable automatic notifications until the print ends"),
    CommandDefinition("/dontshutup", CmdDontShutup, "Make the bot talk again (opposite of /shutup)"),
    CommandDefinition("/help", CmdHelp, "Show available commands", available_to_everyone=True),
    CommandDefinition("/start", CmdStart, "Start the bot", available_to_everyone=True),
    CommandDefinition("close", CmdClose, "Cancel action", available_to_everyone=True),
)

COMMANDS: dict[str, CommandDefinition] = {command.name: command for command in COMMAND_DEFINITIONS}


def get(name: str) -> CommandDefinition | None:
    """Return the definition of a command, or None if the name is unknown."""
    return COMMANDS.get(name)


def configurable_per_chat() -> list[CommandDefinition]:
    """Commands whose permissions are configurable per chat."""
    return [command for command in COMMAND_DEFINITIONS if not command.available_to_everyone]


def shown_to_users() -> list[CommandDefinition]:
    """Commands offered in the Telegram command list and in /help."""
    return [command for command in COMMAND_DEFINITIONS if command.shown_to_users]
