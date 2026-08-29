from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING

from .hooks import ImageHookMethod, ImageHooks
from .snapshots import Snapshots
from .video import FfmpegPreset, Video
from .webcams import WebcamProfile, Webcams

if TYPE_CHECKING:
    from octoprint.events import EventManager
    from octoprint.plugin.core import PluginManager
    from octoprint.printer import PrinterInterface

    from ..core.settings import OctoPrintSettings, Settings
    from ..integrations.plugins import Plugins


class Media:
    """Pictures and videos taken from the webcams."""

    def __init__(
        self,
        settings: Settings,
        octoprint_settings: OctoPrintSettings,
        plugins: Plugins,
        plugin_manager: PluginManager,
        printer: PrinterInterface,
        event_manager: EventManager,
        data_folder: str,
        logger: logging.Logger,
    ) -> None:
        """Set up the taking of pictures and videos from the webcams.

        Args:
            settings (Settings): The plugin settings.
            octoprint_settings (OctoPrintSettings): The settings stored by OctoPrint itself.
            plugins (Plugins): The OctoPrint plugins installed.
            plugin_manager (PluginManager): The OctoPrint plugin manager.
            printer (PrinterInterface): The printer.
            event_manager (EventManager): The OctoPrint event bus.
            data_folder (str): The folder the videos are written to.
            logger (logging.Logger): The logger to write to.
        """
        self.webcams = Webcams(plugin_manager, plugins, octoprint_settings, logger)
        self.snapshots = Snapshots(self.webcams, logger)
        self.video = Video(self.webcams, settings, octoprint_settings, data_folder, logger)
        self.hooks = ImageHooks(settings, printer, event_manager, logger)

    def clear_temporary_files(self) -> None:
        """Discard any video left over from a previous run."""
        shutil.rmtree(self.video.temporary_directory, ignore_errors=True)
        os.makedirs(self.video.temporary_directory, exist_ok=True)


__all__ = ["FfmpegPreset", "ImageHookMethod", "ImageHooks", "Media", "Snapshots", "Video", "WebcamProfile", "Webcams"]
