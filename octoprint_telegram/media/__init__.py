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
    from ..core.settings import OctoPrintSettings, Settings
    from ..integrations.plugins import Plugins


class Media:
    """Pictures and videos taken from the webcams."""

    def __init__(
        self,
        settings: Settings,
        octoprint_settings: OctoPrintSettings,
        plugins: Plugins,
        plugin_manager,
        printer,
        event_manager,
        data_folder: str,
        logger: logging.Logger,
    ):
        self.webcams = Webcams(plugin_manager, plugins, octoprint_settings, logger)
        self.snapshots = Snapshots(self.webcams, logger)
        self.video = Video(self.webcams, settings, octoprint_settings, data_folder, logger)
        self.hooks = ImageHooks(settings, printer, event_manager, logger)

    def clear_temporary_files(self) -> None:
        """Discard any video left over from a previous run."""
        shutil.rmtree(self.video.temporary_directory, ignore_errors=True)
        os.makedirs(self.video.temporary_directory, exist_ok=True)


__all__ = ["FfmpegPreset", "ImageHookMethod", "ImageHooks", "Media", "Snapshots", "Video", "WebcamProfile", "Webcams"]
