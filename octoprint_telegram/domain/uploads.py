from __future__ import annotations

import html
import io
import os
import zipfile
from typing import TYPE_CHECKING

import octoprint.filemanager

from ..emoji import Emoji
from ..telegram import Markup
from . import permissions
from .files import is_file_busy

if TYPE_CHECKING:
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis

UPLOAD_FOLDER_NAME = "TelegramPlugin"


class Uploads:
    """The files users send to the bot, stored into the OctoPrint file library."""

    MAX_LISTED_FILES = 10

    MAX_ZIP_FILES = 300
    MAX_ZIP_UNCOMPRESSED_FILE_MEGABYTES = 1024
    MAX_ZIP_UNCOMPRESSED_TOTAL_MEGABYTES = 3 * 1024

    def __init__(self, plugin_context: PluginContext) -> None:
        """Set up the handling of the files users send to the bot.

        Args:
            plugin_context (PluginContext): The plugin context.
        """
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("Uploads")

    def store_document(self, message: dict, chat_id: str, from_id: str, msg_id_to_reply_to: str = "") -> None:
        """Store into the OctoPrint file library a file a user sent to the bot.

        Args:
            message (dict): The Telegram message carrying the document.
            chat_id (str): The chat the document was sent from.
            from_id (str): The id of the user who sent the document.
            msg_id_to_reply_to (str, optional): The message the answer is a reply to.
        """
        try:
            self._logger.debug("Handling document message: %s", message)

            uploaded_file_filename = os.path.basename(message["document"]["file_name"])

            # Check if upload command is allowed
            if not permissions.is_command_allowed(self.plugin_context.settings, chat_id, from_id, "/upload"):
                self._logger.warning("Received file %s from an unauthorized user", uploaded_file_filename)
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:notallowed} You are not authorized to upload files!"),
                    chat_id,
                    reply_to_message_id=msg_id_to_reply_to,
                )
                return

            # Check the file extension
            is_zip_file = uploaded_file_filename.lower().endswith(".zip")

            if not is_zip_file and not octoprint.filemanager.valid_file_type(uploaded_file_filename):
                self._logger.warning("Received file %s with invalid extension", uploaded_file_filename)

                supported_extensions = ", ".join(
                    [f"<code>{html.escape(f'.{ext}')}</code>" for ext in octoprint.filemanager.get_all_extensions()]
                )

                msg = render_emojis(
                    "{emo:notallowed} Sorry, I only accept the following file extensions: "
                    f"{supported_extensions}, or a ZIP file containing them."
                )

                self.plugin_context.sender.send_message(
                    msg, chat_id, markup=Markup.HTML, reply_to_message_id=msg_id_to_reply_to
                )

                return

            # Download the uploaded file
            saving_file_msg_id = (
                self.plugin_context.sender.send_message(
                    render_emojis(f"{{emo:save}} Saving file <code>{html.escape(uploaded_file_filename)}</code>..."),
                    chat_id,
                    markup=Markup.HTML,
                    reply_to_message_id=msg_id_to_reply_to,
                )
                or ""
            )

            uploaded_file_content = self.plugin_context.telegram_client.download_file(message["document"]["file_id"])

            # Prepare the destination folder
            destination_folder = self.plugin_context.file_manager.add_folder(
                octoprint.filemanager.FileDestinations.LOCAL,
                UPLOAD_FOLDER_NAME,
                ignore_existing=True,
            )

            # Save the file on disk
            added_files_relative_paths = []
            skipped_busy_files = []
            if is_zip_file:
                zip_file = io.BytesIO(uploaded_file_content)
                with zipfile.ZipFile(zip_file, "r") as zf:
                    zip_members = [member for member in zf.infolist() if not member.is_dir()]
                    declared_total_size = sum(member.file_size for member in zip_members)

                    rejection_reason = ""
                    if len(zip_members) > self.MAX_ZIP_FILES:
                        rejection_reason = f"it contains more than {self.MAX_ZIP_FILES} files"
                    elif any(
                        member.file_size > self.MAX_ZIP_UNCOMPRESSED_FILE_MEGABYTES * 1024 * 1024
                        for member in zip_members
                    ):
                        rejection_reason = (
                            f"it contains a file larger than {self.MAX_ZIP_UNCOMPRESSED_FILE_MEGABYTES}MB uncompressed"
                        )
                    elif declared_total_size > self.MAX_ZIP_UNCOMPRESSED_TOTAL_MEGABYTES * 1024 * 1024:
                        rejection_reason = (
                            f"its content is larger than {self.MAX_ZIP_UNCOMPRESSED_TOTAL_MEGABYTES}MB uncompressed"
                        )

                    if rejection_reason:
                        self._logger.warning(
                            "Rejecting zip %s: %s (%s files and %s bytes declared in total)",
                            uploaded_file_filename,
                            rejection_reason,
                            len(zip_members),
                            declared_total_size,
                        )
                        self.plugin_context.sender.send_message(
                            render_emojis(
                                f"{{emo:notallowed}} I can't extract <code>{html.escape(uploaded_file_filename)}</code>: "
                                f"{rejection_reason}."
                            ),
                            chat_id,
                            markup=Markup.HTML,
                            message_id=saving_file_msg_id,
                        )
                        return

                    for member in zf.infolist():
                        member_path_parts = [
                            part
                            for part in member.filename.replace("\\", "/").split("/")
                            if part not in ("", ".", "..")
                        ]
                        member_filename = member_path_parts[-1] if member_path_parts else ""

                        try:
                            # Don't extract folders
                            if member.is_dir() or not member_filename:
                                self._logger.debug(
                                    "Ignoring entry %s while extracting a zip because it's not a file", member.filename
                                )
                                continue

                            # Don't extract file with invalid extensions
                            if not octoprint.filemanager.valid_file_type(member_filename):
                                self._logger.debug(
                                    "Ignoring file %s while extracting a zip because it has an invalid extension",
                                    member_filename,
                                )
                                continue

                            member_destination_folder = destination_folder
                            for member_folder_name in member_path_parts[:-1]:
                                member_destination_folder = self.plugin_context.file_manager.add_folder(
                                    octoprint.filemanager.FileDestinations.LOCAL,
                                    self.plugin_context.file_manager.join_path(
                                        octoprint.filemanager.FileDestinations.LOCAL,
                                        member_destination_folder,
                                        member_folder_name,
                                    ),
                                    ignore_existing=True,
                                )

                            destination_file_relative_path = self.plugin_context.file_manager.join_path(
                                octoprint.filemanager.FileDestinations.LOCAL, member_destination_folder, member_filename
                            )

                            if is_file_busy(
                                self.plugin_context.printer,
                                self.plugin_context.file_manager,
                                octoprint.filemanager.FileDestinations.LOCAL,
                                destination_file_relative_path,
                            ):
                                self._logger.warning(
                                    "Not overwriting %s because it is currently in use", destination_file_relative_path
                                )
                                skipped_busy_files.append(destination_file_relative_path)
                                continue

                            with zf.open(member) as member_stream:
                                stream_wrapper = octoprint.filemanager.util.StreamWrapper(
                                    destination_file_relative_path,
                                    member_stream,
                                )

                                added_file_relative_path = self.plugin_context.file_manager.add_file(
                                    octoprint.filemanager.FileDestinations.LOCAL,
                                    destination_file_relative_path,
                                    stream_wrapper,
                                    allow_overwrite=True,
                                )
                            self._logger.info("Added file to %s", added_file_relative_path)

                            added_files_relative_paths.append(added_file_relative_path)
                        except Exception:
                            self._logger.exception(
                                "Exception while extracting file %s contained in the zip", member_filename
                            )
            else:
                destination_file_relative_path = self.plugin_context.file_manager.join_path(
                    octoprint.filemanager.FileDestinations.LOCAL, destination_folder, uploaded_file_filename
                )

                if is_file_busy(
                    self.plugin_context.printer,
                    self.plugin_context.file_manager,
                    octoprint.filemanager.FileDestinations.LOCAL,
                    destination_file_relative_path,
                ):
                    self._logger.warning(
                        "Not overwriting %s because it is currently in use", destination_file_relative_path
                    )
                    self.plugin_context.sender.send_message(
                        render_emojis(
                            f"{{emo:notallowed}} I can't save <code>{html.escape(uploaded_file_filename)}</code>: "
                            "it would overwrite a file that is currently in use."
                        ),
                        chat_id,
                        markup=Markup.HTML,
                        message_id=saving_file_msg_id,
                    )
                    return

                stream_wrapper = octoprint.filemanager.util.StreamWrapper(
                    destination_file_relative_path, io.BytesIO(uploaded_file_content)
                )

                added_file_relative_path = self.plugin_context.file_manager.add_file(
                    octoprint.filemanager.FileDestinations.LOCAL,
                    destination_file_relative_path,
                    stream_wrapper,
                    allow_overwrite=True,
                )
                self._logger.info("Added file to %s", added_file_relative_path)

                added_files_relative_paths.append(added_file_relative_path)

            # Update the "saving file" message
            command_buttons = None
            skipped_note = ""
            if skipped_busy_files:
                skipped_note = render_emojis(
                    "\n\n{emo:warning} I didn't save "
                    f"{', '.join(f'<code>{html.escape(path)}</code>' for path in skipped_busy_files)} "
                    "because currently in use."
                )

            if added_files_relative_paths:
                if len(added_files_relative_paths) > self.MAX_LISTED_FILES:
                    response_message = render_emojis(
                        f"{{emo:download}} I've successfully saved the {len(added_files_relative_paths)} files "
                        "you sent me."
                    )
                else:
                    response_message = render_emojis(
                        "{emo:download} I've successfully saved the file"
                        f"{'s' if len(added_files_relative_paths) > 1 else ''} you sent me as "
                        f"{', '.join(f'<code>{html.escape(path)}</code>' for path in added_files_relative_paths)}."
                    )

                response_message += skipped_note

                if len(added_files_relative_paths) == 1:
                    if (
                        octoprint.filemanager.valid_file_type(added_files_relative_paths[0], "model")
                        and self.plugin_context.slicing_manager.slicing_enabled
                    ):
                        response_message += render_emojis("\n\n{emo:slice} You can slice it using the /files command.")
                    elif self.plugin_context.settings.select_file_after_upload:
                        # Check if printer is ready
                        if not self.plugin_context.printer.is_ready():
                            response_message += render_emojis(
                                "\n\n{emo:attention} But I couldn't select it for printing because the printer is not ready."
                            )
                        else:
                            # Select for printing the uploaded file
                            try:
                                file_relative_path = added_files_relative_paths[0]
                                self._logger.debug("Selecting file: %s", file_relative_path)
                                if hasattr(self.plugin_context.printer, "set_job"):
                                    # OctoPrint >= 2.0.0
                                    job = self.plugin_context.file_manager.create_job(
                                        octoprint.filemanager.FileDestinations.LOCAL,
                                        file_relative_path,
                                    )
                                    self.plugin_context.printer.set_job(job, print_after_select=False)
                                else:
                                    # OctoPrint < 2.0.0 backwards compatibility
                                    # nosemgrep (this is a fallback for older OctoPrint versions)
                                    self.plugin_context.printer.select_file(
                                        self.plugin_context.file_manager.path_on_disk(
                                            octoprint.filemanager.FileDestinations.LOCAL,
                                            file_relative_path,
                                        ),
                                        sd=False,
                                        printAfterSelect=False,
                                    )

                                # Ask the user whether to print the file
                                response_message += render_emojis(
                                    "\n\n{emo:check} The file has been selected for printing.\n"
                                    "{emo:question} Do you want to start printing it now?"
                                )
                                command_buttons = [
                                    [
                                        (
                                            render_emojis("{emo:check} Print"),
                                            "/print_yes",
                                        ),
                                        (
                                            render_emojis("{emo:cancel} Close"),
                                            "close",
                                        ),
                                    ]
                                ]
                            except Exception:
                                response_message += render_emojis(
                                    "\n{emo:attention} But I wasn't able to select the file for printing."
                                )
            elif skipped_busy_files:
                response_message = render_emojis("{emo:warning} No files were saved.") + skipped_note
            else:
                response_message = render_emojis("{emo:warning} No files were saved. Did you upload an empty zip?")

            self.plugin_context.sender.send_message(
                response_message,
                chat_id,
                markup=Markup.HTML,
                buttons=command_buttons,
                message_id=saving_file_msg_id,
            )
        except Exception:
            self._logger.exception("Caught an exception in store_document")
            self.plugin_context.sender.send_message(
                render_emojis("{emo:attention} Something went wrong processing your file. Please check logs."),
                chat_id,
                reply_to_message_id=msg_id_to_reply_to,
            )
