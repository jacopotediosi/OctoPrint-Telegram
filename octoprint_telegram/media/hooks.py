from __future__ import annotations

import logging
import subprocess
import time
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octoprint.events import EventManager
    from octoprint.printer import PrinterInterface

    from ..core.settings import Settings


class ImageHookMethod(Enum):
    """How a hook around taking a webcam image is run."""

    NONE = "None"
    EVENT = "EVENT"
    GCODE = "GCODE"
    SYSTEM = "SYSTEM"


class ImageHooks:
    """The user-configured actions run around taking a webcam image."""

    def __init__(
        self, settings: Settings, printer: PrinterInterface, event_manager: EventManager, logger: logging.Logger
    ) -> None:
        self._settings = settings
        self._printer = printer
        self._event_manager = event_manager
        self._logger = logger.getChild("ImageHooks")

    def run_before_image(self) -> None:
        method_setting = self._settings.pre_img_method

        try:
            method = ImageHookMethod(method_setting)
        except ValueError:
            self._logger.warning("Unknown pre_image method: %s", method_setting)
            return

        if method is ImageHookMethod.NONE:
            return

        command = self._settings.pre_img_command
        delay = self._settings.pre_img_delay

        self._logger.debug("Executing pre_image: method=%s, command=%s, delay=%ss", method.value, command, delay)

        if method is ImageHookMethod.EVENT:
            self._event_manager.fire("plugin_telegram_preimg")
        elif method is ImageHookMethod.GCODE:
            self._printer.commands(command)
            self._logger.debug("Pre_image gcode command sent")
        elif method is ImageHookMethod.SYSTEM:
            try:
                proc = subprocess.Popen(command, shell=True)
                self._logger.debug("Pre_image SYSTEM command started (PID=%s)", proc.pid)
                proc.wait()
                self._logger.debug("Pre_image SYSTEM command finished with return code %s", proc.returncode)
            except Exception:
                self._logger.exception("Caught an exception running pre_image SYSTEM command '%s'", command)

        if delay:
            self._logger.debug("Pre_image: sleeping for %ss", delay)
            time.sleep(delay)

    def run_after_image(self) -> None:
        method_setting = self._settings.post_img_method

        try:
            method = ImageHookMethod(method_setting)
        except ValueError:
            self._logger.warning("Unknown post_image method: %s", method_setting)
            return

        if method is ImageHookMethod.NONE:
            return

        command = self._settings.post_img_command
        delay = self._settings.post_img_delay

        self._logger.debug("Executing post_image: method=%s, command=%s, delay=%ss", method.value, command, delay)

        if delay:
            self._logger.debug("Post_image: sleeping for %ss", delay)
            time.sleep(delay)

        if method is ImageHookMethod.EVENT:
            self._event_manager.fire("plugin_telegram_postimg")
        elif method is ImageHookMethod.GCODE:
            self._printer.commands(command)
            self._logger.debug("Post_image gcode command sent")
        elif method is ImageHookMethod.SYSTEM:
            try:
                proc = subprocess.Popen(command, shell=True)
                self._logger.debug("Post_image SYSTEM command started (PID=%s)", proc.pid)
                proc.wait()
                self._logger.debug("Post_image SYSTEM command finished with return code %s", proc.returncode)
            except Exception:
                self._logger.exception("Caught an exception running post_image SYSTEM command '%s'", command)
