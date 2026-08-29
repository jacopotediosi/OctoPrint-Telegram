from __future__ import annotations

import io
import logging
from urllib.parse import urljoin

import requests
from PIL import Image

from .webcams import WebcamProfile, Webcams


class Snapshots:
    """Still pictures taken from the webcams."""

    def __init__(self, webcams: Webcams, logger: logging.Logger) -> None:
        self._webcams = webcams
        self._logger = logger.getChild("Snapshots")

    def take_all_images(self) -> list[bytes]:
        taken_images_contents = []

        self._logger.debug("Taking all images")

        webcam_profiles = self._webcams.get_webcam_profiles()
        for webcam_profile in webcam_profiles:
            try:
                if not webcam_profile.provider and not webcam_profile.snapshot:
                    self._logger.debug("Skipped a webcam unable to take snapshots")
                    continue

                taken_image_content = self.take_image(webcam_profile)
                taken_images_contents.append(taken_image_content)
            except Exception:
                self._logger.exception("Caught an exception taking an image")

        return taken_images_contents

    def take_image(self, webcam_profile: WebcamProfile) -> bytes:
        image_content = None

        if webcam_profile.provider:
            try:
                self._logger.debug("Taking image of webcam %s through its provider", webcam_profile.name)

                snapshot = webcam_profile.provider.take_webcam_snapshot(webcam_profile.name)

                if isinstance(snapshot, (bytes, bytearray)):
                    image_content = bytes(snapshot)
                else:
                    image_content = b"".join(chunk for chunk in snapshot if chunk)
            except Exception:
                self._logger.exception(
                    "Caught an exception taking an image of webcam %s through its provider",
                    webcam_profile.name,
                )

        if image_content is None:
            if webcam_profile.snapshot:
                snapshot_url = urljoin("http://localhost/", webcam_profile.snapshot)

                self._logger.debug("Taking image of webcam %s from url %s", webcam_profile.name, snapshot_url)

                r = requests.get(
                    snapshot_url,
                    timeout=webcam_profile.snapshotTimeout,
                    verify=webcam_profile.snapshotSslValidation,
                )
                r.raise_for_status()

                image_content = r.content
            else:
                self._logger.error("Webcam %s has no snapshot url", webcam_profile.name)

        if image_content is None:
            raise RuntimeError(f"Unable to take an image of webcam {webcam_profile.name}")

        flipH = webcam_profile.flipH
        flipV = webcam_profile.flipV
        rotate = webcam_profile.rotate90

        with io.BytesIO(image_content) as image_buffer, Image.open(image_buffer) as image:
            image.load()

            if any([flipH, flipV, rotate]):
                self._logger.debug(
                    "Applying image transformations: flipH=%s, flipV=%s, rotate=%s", flipH, flipV, rotate
                )

                if flipH:
                    image = image.transpose(Image.FLIP_LEFT_RIGHT)  # ty: ignore[unresolved-attribute]
                if flipV:
                    image = image.transpose(Image.FLIP_TOP_BOTTOM)  # ty: ignore[unresolved-attribute]
                if rotate:
                    image = image.transpose(Image.ROTATE_90)  # ty: ignore[unresolved-attribute]

            with io.BytesIO() as output:
                image.save(output, format="JPEG")
                return output.getvalue()
