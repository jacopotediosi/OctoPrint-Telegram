from __future__ import annotations

import os
import shutil


def resolve_ffmpeg_path(configured_path: str | None) -> str | None:
    """Find the ffmpeg binary to run.

    Args:
        configured_path (str | None): The path of ffmpeg configured in OctoPrint.

    Returns:
        str | None: The path of the binary, or None when ffmpeg is not installed.
    """
    if isinstance(configured_path, str) and os.path.isfile(configured_path) and os.access(configured_path, os.X_OK):
        return configured_path
    return shutil.which("ffmpeg")


def resolve_cpulimiter_path() -> str | None:
    """Find the CPU limiter binary to run.

    Returns:
        str | None: The path of the binary, or None when no CPU limiter is installed.
    """
    return shutil.which("cpulimit") or shutil.which("limitcpu")
