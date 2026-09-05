from __future__ import annotations

import multiprocessing
import shutil
import subprocess
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from ..utils import kill_process_group, resolve_cpulimiter_path, resolve_ffmpeg_path

if TYPE_CHECKING:
    import logging

    from ..core.settings import OctoPrintSettings, Settings
    from .webcams import Webcams

FFMPEG_TIMEOUT_SECONDS = 600


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
        logger: logging.Logger,
    ) -> None:
        """Set up the recording of the webcam streams.

        Args:
            webcams (Webcams): The webcams the videos are recorded from.
            settings (Settings): The plugin settings.
            octoprint_settings (OctoPrintSettings): The settings stored by OctoPrint itself.
            logger (logging.Logger): The logger to write to.
        """
        self._webcams = webcams
        self._settings = settings
        self._octoprint_settings = octoprint_settings
        self._logger = logger.getChild("Video")

    def take_all_gifs(self, duration: int = 5) -> list[bytes]:
        """Record a video from every webcam.

        Args:
            duration (int, optional): The seconds to record from each webcam.

        Returns:
            list[bytes]: The content of each video recorded.
        """
        taken_gifs_contents = []

        self._logger.debug("Taking all gifs")

        webcam_profiles = self._webcams.get_webcam_profiles()
        for webcam_profile in webcam_profiles:
            try:
                if not webcam_profile.stream:
                    self._logger.debug("Skipped a webcam without stream url")
                    continue

                taken_gif_content = self.take_gif(
                    webcam_profile.stream,
                    duration,
                    webcam_profile.flipH,
                    webcam_profile.flipV,
                    webcam_profile.rotate90,
                )
                taken_gifs_contents.append(taken_gif_content)
            except Exception:
                self._logger.exception("Caught an exception taking a gif")

        return taken_gifs_contents

    def take_gif(
        self,
        stream_url: str,
        duration: int = 5,
        flipH: bool = False,
        flipV: bool = False,
        rotate: bool = False,
    ) -> bytes:
        """Record a video from a single webcam stream.

        Args:
            stream_url (str): The URL of the stream to record.
            duration (int, optional): The seconds to record, brought back within 1 and 60.
            flipH (bool, optional): Whether the image is flipped horizontally.
            flipV (bool, optional): Whether the image is flipped vertically.
            rotate (bool, optional): Whether the image is rotated by 90 degrees.

        Returns:
            bytes: The content of the video recorded.

        Raises:
            RuntimeError: If ffmpeg or the CPU limiter is not installed, or the recording produced no video.
            subprocess.CalledProcessError: If ffmpeg exits with an error.
            subprocess.TimeoutExpired: If the recording does not finish in time.
        """
        stream_url = urljoin("http://localhost/", stream_url)

        self._logger.debug("Taking gif from url: %s", stream_url)

        ffmpeg_path = resolve_ffmpeg_path(self._octoprint_settings.ffmpeg_path)
        if not ffmpeg_path:
            self._logger.error("ffmpeg not installed")
            raise RuntimeError("ffmpeg not installed")

        cpulimiter_path = resolve_cpulimiter_path()
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
            # Fragmented output
            "-movflags", "frag_keyframe+empty_moov",
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

        cmd += ["-f", "mp4", "pipe:1"]

        self._logger.debug("Creating video by running command: %s", cmd)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, start_new_session=True)  # noqa: S603
        try:
            stdout, _ = process.communicate(timeout=FFMPEG_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            kill_process_group(process)
            process.communicate()
            raise
        self._logger.debug("Video created")

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)

        if not stdout:
            raise RuntimeError("The recording produced no video")

        return stdout
