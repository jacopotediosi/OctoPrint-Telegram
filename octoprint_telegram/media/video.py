from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
import subprocess
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from werkzeug.utils import secure_filename

from .webcams import Webcams

if TYPE_CHECKING:
    from ..core.settings import OctoPrintSettings, Settings

TEMPORARY_DIRECTORY_NAME = "tmpgif"


class FfmpegPreset(Enum):
    """The encoding speed ffmpeg is run with."""

    ULTRAFAST = "ultrafast"
    SUPERFAST = "superfast"
    VERYFAST = "veryfast"
    FASTER = "faster"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    SLOWER = "slower"
    VERYSLOW = "veryslow"


class Video:
    """Videos recorded from the webcam streams."""

    def __init__(
        self,
        webcams: Webcams,
        settings: Settings,
        octoprint_settings: OctoPrintSettings,
        data_folder: str,
        logger: logging.Logger,
    ) -> None:
        self._webcams = webcams
        self._settings = settings
        self._octoprint_settings = octoprint_settings
        self._data_folder = data_folder
        self._logger = logger.getChild("Video")

    @property
    def temporary_directory(self) -> str:
        """The folder recorded videos are written to."""
        return os.path.join(self._data_folder, TEMPORARY_DIRECTORY_NAME)

    def take_all_gifs(self, duration: int = 5) -> list[str]:
        taken_gif_paths = []

        self._logger.debug("Taking all gifs")

        webcam_profiles = self._webcams.get_webcam_profiles()
        for webcam_profile in webcam_profiles:
            try:
                if not webcam_profile.stream:
                    self._logger.debug("Skipped a webcam without stream url")
                    continue

                profile_name = webcam_profile.name or "default"
                gif_filename = secure_filename(f"gif_{profile_name}.mp4")

                taken_gif_path = self.take_gif(
                    webcam_profile.stream,
                    duration,
                    gif_filename,
                    webcam_profile.flipH,
                    webcam_profile.flipV,
                    webcam_profile.rotate90,
                )
                taken_gif_paths.append(taken_gif_path)
            except Exception:
                self._logger.exception("Caught an exception taking a gif")

        return taken_gif_paths

    def take_gif(
        self,
        stream_url: str,
        duration: int = 5,
        gif_filename: str = "gif.mp4",
        flipH: bool = False,
        flipV: bool = False,
        rotate: bool = False,
    ) -> str:
        stream_url = urljoin("http://localhost/", stream_url)

        self._logger.debug("Taking gif from url: %s", stream_url)

        gif_path = os.path.join(self.temporary_directory, gif_filename)

        self._logger.debug("Removing file %s", gif_path)
        try:
            os.remove(gif_path)
        except FileNotFoundError:
            pass

        settings_ffmpeg = self._octoprint_settings.ffmpeg_path
        ffmpeg_path = (
            settings_ffmpeg
            if isinstance(settings_ffmpeg, str)
            and os.path.isfile(settings_ffmpeg)
            and os.access(settings_ffmpeg, os.X_OK)
            else shutil.which("ffmpeg")
        )
        if not ffmpeg_path:
            self._logger.error("ffmpeg not installed")
            raise RuntimeError("ffmpeg not installed")

        cpulimiter_path = shutil.which("cpulimit") or shutil.which("limitcpu")
        cpulimiter_disabled = self._settings.no_cpulimit
        if cpulimiter_disabled:
            self._logger.debug("CPU limiter disabled via settings")
        elif cpulimiter_path:
            self._logger.debug("Using CPU limiter: %s", cpulimiter_path)
        else:
            self._logger.error("Neither cpulimit nor limitcpu is installed")
            raise RuntimeError("No CPU limiter (cpulimit or limitcpu) available")

        duration = max(1, min(duration, 60))
        self._logger.debug("duration=%s", duration)

        time_sec = str(timedelta(seconds=duration))
        self._logger.debug("timeSec=%s", time_sec)

        used_cpu, limit_cpu = 1, 65
        try:
            nb_cpu = multiprocessing.cpu_count()
            if nb_cpu > 1:
                used_cpu = nb_cpu // 2
                limit_cpu = 65 * used_cpu
            self._logger.debug("limit_cpu=%s | used_cpu=%s | because nb_cpu=%s", limit_cpu, used_cpu, nb_cpu)
        except Exception:
            self._logger.exception("Caught an exception getting number of cpu. Using defaults...")

        preset_setting = self._settings.ffmpeg_preset
        try:
            preset = FfmpegPreset(preset_setting)
        except ValueError:
            self._logger.warning(
                "Unknown ffmpeg preset '%s', falling back to '%s'", preset_setting, FfmpegPreset.MEDIUM.value
            )
            preset = FfmpegPreset.MEDIUM

        cmd = []
        if shutil.which("nice"):
            cmd = ["nice", "-n", "20"]

        if cpulimiter_path and not cpulimiter_disabled:
            cmd += [
                cpulimiter_path,
                "-l",
                str(limit_cpu),
                "-f",
                "-z",
                "--",
            ]

        cmd += [
            ffmpeg_path,
            # Overwrite output file
            "-y",
            # Limit threads
            "-threads", str(used_cpu),
            # Video source
            "-i", str(stream_url),
            # Duration
            "-t", str(time_sec),
            # Video encoding
            "-color_range", "tv",
            "-c:v", "libx264",
            "-preset", preset.value,
            "-profile:v", "baseline",
            # Audio encoding
            "-c:a", "aac",
            "-ac", "2",
            # Enable fast start for streaming
            "-movflags", "+faststart",
        ]  # fmt: skip

        filters = ["format=yuv420p"]

        if flipV:
            filters.append("vflip")
        if flipH:
            filters.append("hflip")
        if rotate:
            filters.append("transpose=2")

        filter_str = ",".join(filters)
        cmd += ["-vf", filter_str]

        cmd.append(gif_path)

        self._logger.debug("Creating video by running command: %s", cmd)
        subprocess.run(cmd, check=True)
        self._logger.debug("Video created")

        if not os.path.isfile(gif_path):
            raise FileNotFoundError("Expected gif file was not created: %s", gif_path)

        return gif_path
