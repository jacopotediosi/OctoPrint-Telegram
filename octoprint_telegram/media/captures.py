from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from .hooks import ImageHooks
    from .snapshots import Snapshots
    from .video import Video


class CaptureJob:
    """A capture request and its result."""

    def __init__(self, kind: str, gif_duration: int = 0) -> None:
        """Set up the capture request.

        Args:
            kind (str): What to capture, either "images" or "gifs".
            gif_duration (int, optional): Seconds of video to record from each webcam, when videos are captured.
        """
        self.kind = kind
        self.gif_duration = gif_duration
        self.done = threading.Event()
        self.result: list[bytes] = []


class Captures:
    """Pictures and videos captured from the webcams."""

    def __init__(self, snapshots: Snapshots, video: Video, hooks: ImageHooks, logger: logging.Logger) -> None:
        """Set up the capturing of pictures and videos.

        Args:
            snapshots (Snapshots): The still pictures taken from the webcams.
            video (Video): The videos recorded from the webcam streams.
            hooks (ImageHooks): The hooks run before and after the captures.
            logger (logging.Logger): The logger to write to.
        """
        self._snapshots = snapshots
        self._video = video
        self._hooks = hooks
        self._logger = logger.getChild("Captures")
        self._jobs: dict[tuple[str, int], CaptureJob] = {}
        self._jobs_lock = threading.Lock()
        self._queue: queue.Queue[CaptureJob] = queue.Queue()

        self._worker = threading.Thread(target=self._work, daemon=True)
        self._worker.start()

    def capture_media(self, with_image: bool, with_gif: bool, gif_duration: int = 5) -> tuple[list[bytes], list[bytes]]:
        """Take a snapshot and record a video from every webcam.

        A request equal to one still waiting or already running joins it and receives its result.

        Args:
            with_image (bool): Whether to take the snapshots.
            with_gif (bool): Whether to record the videos.
            gif_duration (int, optional): Seconds of video to record from each webcam.

        Returns:
            tuple[list[bytes], list[bytes]]: The content of the pictures taken, then of the videos recorded.
        """
        jobs = []

        with self._jobs_lock:
            if with_image:
                jobs.append(self._get_or_enqueue_job("images"))
            if with_gif:
                jobs.append(self._get_or_enqueue_job("gifs", gif_duration))

        images, gifs = [], []
        for job in jobs:
            job.done.wait()
            if job.kind == "images":
                images = job.result
            else:
                gifs = job.result

        return images, gifs

    def _get_or_enqueue_job(self, kind: str, gif_duration: int = 0) -> CaptureJob:
        key = (kind, gif_duration)

        job = self._jobs.get(key)
        if job is None:
            job = CaptureJob(kind, gif_duration)
            self._jobs[key] = job
            self._queue.put(job)

        return job

    def _work(self) -> None:
        while True:
            job = self._queue.get()

            # Pre image
            try:
                self._hooks.run_before_image()
            except Exception:
                self._logger.exception("Caught an exception calling run_before_image()")

            # Capture images and gifs
            while True:
                try:
                    self._run_job(job)
                except Exception:
                    self._logger.exception("Caught an exception running a capture")
                finally:
                    with self._jobs_lock:
                        self._jobs.pop((job.kind, job.gif_duration), None)
                    job.done.set()

                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    break

            # Post image
            try:
                self._hooks.run_after_image()
            except Exception:
                self._logger.exception("Caught an exception calling run_after_image()")

    def _run_job(self, job: CaptureJob) -> None:
        if job.kind == "images":
            job.result = self._snapshots.take_all_images()
        else:
            job.result = self._video.take_all_gifs(job.gif_duration)
