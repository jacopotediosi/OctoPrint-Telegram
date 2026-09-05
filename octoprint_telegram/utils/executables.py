from __future__ import annotations

import os
import shutil
import signal
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    import subprocess


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


def kill_process_group(process: subprocess.Popen) -> None:
    """Kill a process and every process it spawned.

    Args:
        process (subprocess.Popen): The process to kill, started with start_new_session=True.
    """
    try:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGKILL)
        else:
            # Windows has no process groups: the children must be listed before
            # killing the parent, which makes them untraceable
            try:
                children = psutil.Process(process.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                children = []
            process.kill()
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
    except ProcessLookupError:
        pass
