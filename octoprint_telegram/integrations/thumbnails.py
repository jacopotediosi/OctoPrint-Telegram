from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from octoprint.filemanager import FileManager

    from .octoprint_api import OctoPrintApi


class Thumbnails:
    """The preview images of the printable files stored in OctoPrint."""

    def __init__(self, file_manager: FileManager, api: OctoPrintApi, logger: logging.Logger) -> None:
        """Set up the thumbnail lookup.

        Args:
            file_manager (FileManager): The OctoPrint file manager the files are stored in.
            api (OctoPrintApi): The OctoPrint HTTP API.
            logger (logging.Logger): The logger to write to.
        """
        self._file_manager = file_manager
        self._api = api
        self._logger = logger.getChild("Thumbnails")

    def get_thumbnail(self, storage_name: str, file_path: str) -> bytes | None:
        """The preview image of a file.

        Args:
            storage_name (str): The storage the file is stored in (e.g., octoprint.filemanager.FileDestinations.LOCAL).
            file_path (str): The path of the file inside its storage.

        Returns:
            bytes or None: The content of the image, or None if the file has no preview image.
        """
        if storage_name not in self._file_manager.registered_storages:
            self._logger.debug("Storage %s is not registered", storage_name)
            return None

        thumbnail = self._get_native_thumbnail(storage_name, file_path)
        if not thumbnail:
            thumbnail = self._get_plugin_thumbnail(storage_name, file_path)
        return thumbnail

    def _get_native_thumbnail(self, storage_name: str, file_path: str) -> bytes | None:
        """The preview image OctoPrint itself extracted from the file, available since OctoPrint 2.0.0."""
        if not hasattr(self._file_manager, "has_thumbnail"):
            # OctoPrint < 2.0.0 has no native thumbnails
            return None

        try:
            if not self._file_manager.capabilities(storage_name).thumbnails:
                self._logger.debug("Storage %s doesn't support thumbnails", storage_name)
                return None

            if not self._file_manager.has_thumbnail(storage_name, file_path):
                self._logger.debug("File %s/%s has no OctoPrint thumbnail", storage_name, file_path)
                return None

            self._logger.debug("Reading the OctoPrint thumbnail of %s/%s", storage_name, file_path)

            thumbnail = self._file_manager.read_thumbnail(storage_name, file_path)
            if not thumbnail:
                return None

            _, thumbnail_handle = thumbnail
            with thumbnail_handle:
                return thumbnail_handle.read()
        except Exception:
            self._logger.exception(
                "Caught an exception reading the OctoPrint thumbnail of %s/%s", storage_name, file_path
            )
            return None

    def _get_plugin_thumbnail(self, storage_name: str, file_path: str) -> bytes | None:
        """The preview image the Slicer Thumbnails plugin extracted from the file."""
        try:
            file_metadata = self._file_manager.get_metadata(storage_name, file_path) or {}

            thumbnail_url = file_metadata.get("thumbnail")
            if not thumbnail_url:
                self._logger.debug("File %s/%s has no Slicer Thumbnails thumbnail", storage_name, file_path)
                return None

            self._logger.debug("Downloading the Slicer Thumbnails thumbnail %s", thumbnail_url)

            return self._api.send_request(f"/{thumbnail_url}").content
        except Exception:
            self._logger.exception(
                "Caught an exception downloading the Slicer Thumbnails thumbnail of %s/%s", storage_name, file_path
            )
            return None
