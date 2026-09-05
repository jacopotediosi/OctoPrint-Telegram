from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octoprint.filemanager import FileManager
    from octoprint.printer import PrinterInterface


def is_file_busy(printer: PrinterInterface, file_manager: FileManager, storage_name: str, file_path: str) -> bool:
    """Whether a file is being printed or sliced.

    Args:
        printer (PrinterInterface): The printer.
        file_manager (FileManager): The OctoPrint file manager.
        storage_name (str): The storage the file is stored in (e.g., octoprint.filemanager.FileDestinations.LOCAL).
        file_path (str): The path of the file inside its storage.

    Returns:
        bool: True if the file is in use.
    """
    current_data = printer.get_current_data() or {}
    job_file = (current_data.get("job") or {}).get("file") or {}
    state_flags = (current_data.get("state") or {}).get("flags") or {}

    # Being printed
    if (
        job_file.get("origin") == storage_name
        and job_file.get("path")
        and file_manager.file_in_path(storage_name, file_path, job_file["path"])
        and any(
            state_flags.get(flag) for flag in ("printing", "paused", "pausing", "resuming", "cancelling", "finishing")
        )
    ):
        return True

    # Being sliced
    return any(
        storage_name == busy_storage and file_manager.file_in_path(storage_name, file_path, busy_path)
        for busy_storage, busy_path in file_manager.get_busy_files()
    )
