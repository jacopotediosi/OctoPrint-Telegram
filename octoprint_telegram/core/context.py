from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octoprint.filemanager import FileManager
    from octoprint.printer import PrinterInterface
    from octoprint.printer.profile import PrinterProfileManager
    from octoprint.slicing import SlicingManager

    from ..commands.registry import CommandDefinition
    from ..domain.chats import Chats
    from ..domain.enrollment import Enrollment
    from ..domain.mute import MutedChats
    from ..integrations.cost import Cost
    from ..integrations.octoprint_api import OctoPrintApi
    from ..integrations.plugins import Plugins
    from ..notifications import Notifications
    from ..telegram.client import TelegramClient
    from ..telegram.sender import Sender
    from .connection_status import ConnectionStatus
    from .frontend import Frontend
    from .settings import OctoPrintSettings, Settings


@dataclass(frozen=True)
class PluginContext:
    """Everything a plugin's component needs to do its work."""

    # Plugin
    logger: logging.Logger
    server_port: int
    commands: tuple[CommandDefinition, ...]

    # Settings
    settings: Settings
    octoprint_settings: OctoPrintSettings

    # Telegram
    telegram_client: TelegramClient
    sender: Sender
    connection_status: ConnectionStatus

    # Plugin settings page
    frontend: Frontend

    # Chats and notifications
    chats: Chats
    muted_chats: MutedChats
    notifications: Notifications
    enrollment: Enrollment

    # OctoPrint services
    printer: PrinterInterface
    printer_profiles: PrinterProfileManager
    file_manager: FileManager
    slicing_manager: SlicingManager

    # Other plugins
    api: OctoPrintApi
    plugins: Plugins
    cost: Cost
