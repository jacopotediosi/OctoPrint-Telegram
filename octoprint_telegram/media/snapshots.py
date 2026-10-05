from __future__ import annotations

import io
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import requests
from PIL import Image

if TYPE_CHECKING:
    import logging

    from .webcams import WebcamProfile, Webcams


class Snapshots:
    """Still pictures taken from the webcams."""

    def __init__(self, webcams: Webcams, logger: logging.Logger) -> None:
        """Set up the taking of snapshots.

        Args:
            webcams (Webcams): The webcams the pictures are taken from.
            logger (logging.Logger): The logger to write to.
        """
        self._webcams = webcams
        self._logger = logger.getChild("Snapshots")

    def take_all_images(self) -> list[bytes]:
        """Take a picture from every webcam.

        Returns:
            list[bytes]: The content of each picture taken.
        """
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
        """Take a picture from a single webcam.

        Args:
            webcam_profile (WebcamProfile): The webcam to take the picture from.

        Returns:
            bytes: The content of the picture taken.

        Raises:
            RuntimeError: If the webcam produced no picture.
        """
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
                    timeout=webcam_profile.snapshot_timeout,
                    verify=webcam_profile.snapshot_ssl_validation,
                )
                r.raise_for_status()

                image_content = r.content
            else:
                self._logger.error("Webcam %s has no snapshot url", webcam_profile.name)

        if image_content is None:
            raise RuntimeError(f"Unable to take an image of webcam {webcam_profile.name}")

        flip_h = webcam_profile.flip_h
        flip_v = webcam_profile.flip_v
        rotate = webcam_profile.rotate90

        with io.BytesIO(image_content) as image_buffer, Image.open(image_buffer) as image:
            image.load()

            transformed_image = image

            if any([flip_h, flip_v, rotate]):
                self._logger.debug(
                    "Applying image transformations: flip_h=%s, flip_v=%s, rotate=%s", flip_h, flip_v, rotate
                )

                if flip_h:
                    transformed_image = transformed_image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if flip_v:
                    transformed_image = transformed_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                if rotate:
                    transformed_image = transformed_image.transpose(Image.Transpose.ROTATE_90)

            if transformed_image.mode != "RGB":
                transformed_image = Image.alpha_composite(
                    Image.new("RGBA", transformed_image.size, "white"),
                    transformed_image.convert("RGBA"),
                ).convert("RGB")

            with io.BytesIO() as output:
                transformed_image.save(output, format="JPEG")
                return output.getvalue()
