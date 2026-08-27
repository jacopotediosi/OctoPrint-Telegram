from __future__ import annotations

import html
import io
import os
import zipfile
from typing import TYPE_CHECKING

import octoprint.filemanager

from ..emoji import Emoji
from ..telegram import HttpMethod, Markup
from . import permissions

if TYPE_CHECKING:
    from ..core.context import PluginContext

render_emojis = Emoji.render_emojis

UPLOAD_FOLDER_NAME = "TelegramPlugin"


class Uploads:
    """The files users send to the bot, stored into the OctoPrint file library."""

    def __init__(self, plugin_context: PluginContext):
        self.plugin_context = plugin_context
        self._logger = plugin_context.logger.getChild("Uploads")

    def store_document(self, message, chat_id, from_id):
        try:
            self._logger.debug("Handling document message: %s", message)

            uploaded_file_filename = os.path.basename(message["document"]["file_name"])

            # Check if upload command is allowed
            if not permissions.is_command_allowed(self.plugin_context.settings, chat_id, from_id, "/upload"):
                self._logger.warning("Received file %s from an unauthorized user", uploaded_file_filename)
                self.plugin_context.sender.send_message(
                    render_emojis("{emo:notallowed} You are not authorized to upload files!"),
                    chat_id,
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

                self.plugin_context.sender.send_message(msg, chat_id, markup=Markup.HTML)

                return

            # Download the uploaded file
            saving_file_response = self.plugin_context.telegram_client.send_request(
                "sendMessage",
                HttpMethod.POST,
                data={
                    "text": render_emojis(
                        f"{{emo:save}} Saving file <code>{html.escape(uploaded_file_filename)}</code>..."
                    ),
                    "chat_id": chat_id,
                    "parse_mode": Markup.HTML.value,
                },
            )
            saving_file_msg_id = saving_file_response["result"]["message_id"]

            uploaded_file_content = self.plugin_context.telegram_client.download_file(message["document"]["file_id"])

            # Prepare the destination folder
            destination_folder = self.plugin_context.file_manager.add_folder(
                octoprint.filemanager.FileDestinations.LOCAL,
                UPLOAD_FOLDER_NAME,
                ignore_existing=True,
            )

            # Save the file on disk
            added_files_relative_paths = []
            if is_zip_file:
                zip_file = io.BytesIO(uploaded_file_content)
                with zipfile.ZipFile(zip_file, "r") as zf:
                    for member in zf.infolist():
                        member_filename = os.path.basename(member.filename)

                        try:
                            # Don't extract folders
                            if member.is_dir():
                                self._logger.debug(
                                    "Ignoring file %s while extracting a zip because it's a folder", member_filename
                                )
                                continue

                            # Don't extract file with invalid extensions
                            if not octoprint.filemanager.valid_file_type(member_filename):
                                self._logger.debug(
                                    "Ignoring file %s while extracting a zip because it has an invalid extension",
                                    member_filename,
                                )
                                continue

                            member_content = zf.read(member)
                            destination_file_relative_path = os.path.join(destination_folder, member_filename)
                            stream_wrapper = octoprint.filemanager.util.StreamWrapper(
                                destination_file_relative_path,
                                io.BytesIO(member_content),
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
                destination_file_relative_path = os.path.join(destination_folder, uploaded_file_filename)
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
            if added_files_relative_paths:
                response_message = render_emojis(
                    "{emo:download} I've successfully saved the file"
                    f"{'s' if len(added_files_relative_paths) > 1 else ''} you sent me as "
                    f"{', '.join(f'<code>{html.escape(path)}</code>' for path in added_files_relative_paths)}."
                )

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
                                        [
                                            render_emojis("{emo:check} Print"),
                                            "/print_y",
                                        ],
                                        [
                                            render_emojis("{emo:cancel} Close"),
                                            "close",
                                        ],
                                    ]
                                ]
                            except Exception:
                                response_message += render_emojis(
                                    "\n{emo:attention} But I wasn't able to select the file for printing."
                                )
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
            )
