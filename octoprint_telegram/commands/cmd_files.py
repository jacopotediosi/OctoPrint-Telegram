import base64
import datetime
import hashlib
import html
from itertools import islice

import octoprint.filemanager
import requests

from ..emoji import Emoji
from ..utils import Formatters
from .base import BaseCommand, CommandContext

get_emoji = Emoji.get_emoji


class CmdFiles(BaseCommand):
    # Number of items (folders + files) to display per page
    PAGE_SIZE = 14

    # HASH_PATH_LENGTH cannot exceed 20 characters in the current implementation
    # because Telegram callback query data is limited to 64 bytes.
    HASH_PATH_LENGTH = 20

    # Mapping from short hash keys to full file/folder paths.
    # Used to overcome Telegram's 64-byte callback query data limit.
    # Each file or folder path gets a unique hash that can be sent in callback queries
    # and later resolved back to the original full path.
    files_hash_path_map = {}

    def execute(self, context: CommandContext):
        """
        Callback query format: /files_operation_pathHash_pageNumber_additionalArg1_additionalArg2

        Parameter instructions:
        - operation: max 8 chars
        - pathHash: 20 chars
        - pageNumber (optional): max 4 chars, it starts from 0 and defaults to 0 if omitted
        - additionalArg1 (optional): max 20 chars (exactly 20 if it is a path hash)
        - additionalArg2 (optional): 1 char

        Operation usage:
        - list:
            - pathHash (optional): the hash of the folder path to list. If omitted, shows storage menu or local storage if it's the only one.
            - pageNumber: the number of the page to display
        - info:
            - pathHash: the hash of the file path to display information about
            - pageNumber: the number of the page to return to with the back button
        - details:
            - pathHash: the hash of the file path to display information about
            - pageNumber: the number of the page to return to with the back button
        - settings:
            - pathHash: the hash of the path to return to with the back button
            - pageNumber: the number of the page to return to with the back button
            - additionalArg1 (optional): "name" = order by name, "date" = order by date, omitted = show selection menu
        - download:
            - pathHash: the hash of the path to download
        - delete:
            - pathHash: the hash of the path to delete
            - pageNumber: the page number to return to after the delete operation
            - additionalArg1 (optional): "yes" = deletion confirmed, omitted = show confirmation menu
        - copy / move:
            - pathHash: the hash of the path to copy/move
            - pageNumber: the page number to return to after the copy/move operation
            - additionalArg1 (optional): the currently selected target path. If omitted, shows storage menu or local storage if it's the only one.
            - additionalArg2 (optional): "a" = ask for confirmation, "y" = copy/move confirmed, omitted = the user is just navigating target paths
        - print:
            - pathHash: the hash of the path to load and print
        """

        if context.parameter:
            # The hash→path map may be empty if the user clicks an old button after restarting the bot.
            # In that case, ask the user to run /files again.
            if not self.files_hash_path_map:
                msg = f"{get_emoji('attention')} This button is no longer valid. Please run {context.cmd} again."
                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
                return

            params = context.parameter.split("_")

            operation = params[0]
            path_hash = params[1] if len(params) > 1 else None
            page_number = int(params[2] or 0) if len(params) > 2 else 0
            additional_arg1 = params[3] if len(params) > 3 else None
            additional_arg2 = params[4] if len(params) > 4 else None

            if operation == "list":
                self.file_list(context, path_hash, page_number)

            elif operation == "info":
                self.file_info(context, path_hash, page_number)

            elif operation == "details":
                self.file_details(context, path_hash, page_number)

            elif operation == "settings":
                self.file_settings(context, path_hash, page_number, additional_arg1)

            elif operation == "download":
                self.file_download(context, path_hash)

            elif operation == "delete":
                self.file_delete(context, path_hash, page_number, additional_arg1)

            elif operation in ("copy", "move"):
                self.file_copy_move(
                    context,
                    path_hash,
                    page_number,
                    additional_arg1,
                    additional_arg2,
                    operation,
                )

            elif operation == "print":
                self.file_print(context, path_hash, page_number)

        else:
            self.file_list(context, None, 0)

    def file_list(self, context: CommandContext, path_hash, page_number):
        try:
            if context.msg_id_to_update:
                self.main.send_msg(
                    f"{get_emoji('loading')} Loading files...",
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
            else:
                loading_files_response = self.main.telegram_utils.send_telegram_request(
                    f"{self.main.bot_url}/sendMessage",
                    "post",
                    data={
                        "text": f"{get_emoji('loading')} Loading files...",
                        "chat_id": context.chat_id,
                    },
                )
                context.msg_id_to_update = loading_files_response["result"]["message_id"]
        except Exception:
            pass

        if not path_hash:  # Show storage selection
            storages = self.list_files(recursive=False)

            if len(storages) == 1:
                storage_name = next(iter(storages))
                storage_hash = self.hash_path(storage_name)
                self.file_list(context, storage_hash, page_number)
            elif len(storages) > 1:
                msg = f"{get_emoji('save')} <b>Select Storage</b>"

                command_buttons = []
                for storage_name in storages:
                    storage_hash = self.hash_path(storage_name)
                    command_buttons.append(
                        [[f"{get_emoji('folder')} {storage_name}", f"{context.cmd}_list_{storage_hash}"]]
                    )
                command_buttons.append([[f"{get_emoji('cancel')} Close", "close"]])

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )

        else:  # List files in path
            path_with_storage = self.files_hash_path_map[path_hash]  # e.g.: local or local/foo
            path_parts = path_with_storage.split("/")
            storage_name = path_parts[0]  # e.g.: local
            path_without_storage = "/".join(path_parts[1:])  # e.g.: '' or foo
            path_is_storage_root = len(path_parts) < 2

            try:
                file_listing = self.list_files(locations=storage_name, path=path_without_storage, recursive=False)
            except Exception:
                msg = f"{get_emoji('attention')} The path you were browsing no longer exists. Perhaps you want to have a look at {context.cmd} again?"
                self.main.send_msg(msg, chatID=context.chat_id, msg_id=context.msg_id_to_update)
                return

            path_content = file_listing.get(storage_name, {})

            # --- Calculate pagination ---
            folders = {name: data for name, data in path_content.items() if data.get("type") == "folder"}
            files = {name: data for name, data in path_content.items() if data.get("type") == "machinecode"}

            total_folders = len(folders)
            total_files = len(files)
            total_items = total_folders + total_files
            total_pages = max(1, (total_items + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

            page_number = max(0, min(page_number, total_pages - 1))
            start_index = page_number * self.PAGE_SIZE
            end_index = start_index + self.PAGE_SIZE

            # --- Create folder buttons (paginated) ---
            sorted_folder_names = sorted(folders.keys())
            paginated_folder_names = sorted_folder_names[start_index : min(len(sorted_folder_names), end_index)]

            folder_buttons = []
            for folder_name in paginated_folder_names:
                folder_hash = self.hash_path(f"{path_with_storage}/{folder_name}")
                folder_buttons.append(
                    [
                        f"{get_emoji('folder')} {folder_name}",
                        f"{context.cmd}_list_{folder_hash}",
                    ]
                )

            # --- Create file buttons (paginated) ---
            # Calculate remaining slots for files after folders
            remaining_slots = end_index - len(paginated_folder_names) - start_index

            file_buttons = []
            if remaining_slots > 0:
                remaining_start = max(0, start_index - len(sorted_folder_names))

                # Sort files
                if self.main._settings.get_boolean(["sort_files_by_date"]):
                    sorted_files = sorted(files.items(), key=lambda x: x[1].get("date", 0), reverse=True)
                else:
                    sorted_files = sorted(files.items())

                # Get only the files for current page
                paginated_files = sorted_files[remaining_start : remaining_start + remaining_slots]

                # Create buttons only for paginated files
                for filename, file_data in paginated_files:
                    file_base_name = filename.rsplit(".", 1)[0]
                    try:
                        if "history" not in file_data:
                            display_filename = f"{get_emoji('new')} {file_base_name}"
                        else:
                            history_list = file_data["history"]
                            if not history_list:
                                display_filename = f"{get_emoji('file')} {file_base_name}"
                            else:
                                history_list.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                                latest_history = history_list[0]

                                if latest_history.get("success"):
                                    display_filename = f"{get_emoji('hooray')} {file_base_name}"
                                else:
                                    display_filename = f"{get_emoji('warning')} {file_base_name}"
                    except Exception:
                        self._logger.exception("Error processing history for file '%s'", filename)
                        display_filename = f"{get_emoji('file')} {file_base_name}"

                    file_hash = self.hash_path(f"{path_with_storage}/{filename}")
                    command = f"{context.cmd}_info_{file_hash}_{page_number}"
                    file_buttons.append([display_filename, command])

            # --- Combine paginated folder and file buttons ---
            paginated_folder_and_file_buttons = folder_buttons + file_buttons

            # --- Create command buttons ---
            command_buttons = []

            # Folder and file buttons
            for i in range(0, len(paginated_folder_and_file_buttons), 2):
                row = paginated_folder_and_file_buttons[i : i + 2]
                command_buttons.append(row)

            # Last row: back, prev/next page, settings, close
            nav_and_actions_row = []

            # Back button (only within subfolders)
            if not path_is_storage_root:
                back_path = "/".join(path_parts[:-1])
                back_path_hash = self.hash_path(back_path)
                nav_and_actions_row.append(
                    [
                        f"{get_emoji('back')} Back",
                        f"{context.cmd}_list_{back_path_hash}",
                    ]
                )

            # Prev/next page
            if total_pages > 1:
                if page_number > 0:
                    nav_and_actions_row.append(
                        [f"{get_emoji('up')} Prev page", f"{context.cmd}_list_{path_hash}_{page_number - 1}"]
                    )
                if page_number + 1 < total_pages:
                    nav_and_actions_row.append(
                        [f"{get_emoji('down')} Next page", f"{context.cmd}_list_{path_hash}_{page_number + 1}"]
                    )

            # Settings and close
            nav_and_actions_row.extend(
                [
                    [
                        f"{get_emoji('settings')} Settings",
                        f"{context.cmd}_settings_{path_hash}_{page_number}",
                    ],
                    [
                        f"{get_emoji('cancel')} Close",
                        "close",
                    ],
                ]
            )

            command_buttons.append(nav_and_actions_row)

            # --- Create message ---
            page_str = f"    [{page_number + 1} / {total_pages}]" if total_pages > 1 else ""
            msg = f"{get_emoji('save')} Files in <code>/{html.escape(path_with_storage)}</code>{page_str}"

            # --- Send message ---
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def file_info(self, context: CommandContext, path_hash, page_number):
        # Lookup file data and metadata
        try:
            storage_name, file_path = self.find_path_by_hash(path_hash)
            _, filename = self.main._file_manager.split_path(storage_name, file_path)
            file_metadata = self.main._file_manager.get_metadata(storage_name, file_path)
            analysis = file_metadata.get("analysis", {})
            history = file_metadata.get("history", [])
        except Exception:
            msg = f"{get_emoji('attention')} I couldn't find the file you were looking for. Perhaps you want to have a look at {context.cmd} again?"
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        # Message header
        msg = f"{get_emoji('info')} <b>File information</b>\n\n"
        msg += f"{get_emoji('name')} <b>Name:</b> <code>{html.escape(filename)}</code>"

        # Upload timestamp
        try:
            lastmodified = self.main._file_manager.get_lastmodified(storage_name, file_path)
            dt = datetime.datetime.fromtimestamp(lastmodified)
            msg += f"\n{get_emoji('calendar')} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            self._logger.exception("Caught an exception getting file date")

        # Print history
        if not history:
            msg += f"\n{get_emoji('new')} <b>Number of Print:</b> 0"
        else:
            try:
                history.sort(key=lambda x: x["timestamp"], reverse=True)
                success = history[0].get("success", False)
                icon = get_emoji("hooray") if success else get_emoji("warning")
            except Exception:
                self._logger.exception("Caught an exception reading history list")
                icon = get_emoji("file")
            msg += f"\n{icon} <b>Number of Print:</b> {len(history)}"

        # File size
        filesize = self.main._file_manager.get_size(storage_name, file_path)
        msg += f"\n{get_emoji('filesize')} <b>Size:</b> {Formatters.format_size(filesize)}"

        # Filament info
        filament_length = 0
        try:
            filament = analysis.get("filament", {})
            if filament:
                msg += f"\n{get_emoji('filament')} <b>Filament:</b> "
                if len(filament) == 1 and "length" in filament.get("tool0", {}):
                    msg += Formatters.format_filament(filament["tool0"])
                    filament_length += float(filament["tool0"]["length"])
                else:
                    for tool in sorted(filament):
                        length = filament[tool].get("length")
                        if length is not None:
                            msg += f"\n      {html.escape(tool)}: {Formatters.format_filament(filament[tool])}"
                            filament_length += float(length)
        except Exception:
            self._logger.exception("Caught an exception getting filament info")

        # Print time
        print_time = analysis.get("estimatedPrintTime")
        if print_time:
            msg += f"\n{get_emoji('stopwatch')} <b>Print Time:</b> {Formatters.format_fuzzy_print_time(print_time)}"

            # ETA
            try:
                time_finish = self.main.calculate_ETA(print_time)
                msg += f"\n{get_emoji('finish')} <b>Completed Time:</b> {html.escape(time_finish)}"
            except Exception:
                self._logger.exception("Caught an exception calculating ETA")

            # Cost calculation (if plugin active)
            if self.main._plugin_manager.get_plugin("cost", True) and filament_length:
                try:
                    cp_h = self.main._settings.global_get_float(["plugins", "cost", "cost_per_time"])
                    cp_m = self.main._settings.global_get_float(["plugins", "cost", "cost_per_length"])
                    curr = self.main._settings.global_get(["plugins", "cost", "currency"])
                    cost = filament_length / 1000 * cp_m + print_time / 3600 * cp_h
                    msg += f"\n{get_emoji('cost')} <b>Cost:</b> {html.escape(curr)}{cost:.02f}"
                except Exception:
                    self._logger.exception("Caught an exception calculating cost")

        # Upload the thumbnail image to imgbb to get a public URL
        imgbb_thumbnail_url = self.upload_thumbnail_to_imgbb(file_metadata)
        if imgbb_thumbnail_url:
            msg = f"<a href='{imgbb_thumbnail_url}'>&#8199;</a>\n{msg}"

        # Create command buttons
        command_buttons = []

        # First row: Print + Details
        first_row = [
            [f"{get_emoji('play')} Print", f"{context.cmd}_print_{path_hash}_{page_number}"],
            [f"{get_emoji('search')} Details", f"{context.cmd}_details_{path_hash}_{page_number}"],
        ]
        command_buttons.append(first_row)

        # Second row: File ops
        second_row = [
            [f"{get_emoji('cut')} Move", f"{context.cmd}_move_{path_hash}_{page_number}"],
            [f"{get_emoji('copy')} Copy", f"{context.cmd}_copy_{path_hash}_{page_number}"],
            [f"{get_emoji('delete')} Delete", f"{context.cmd}_delete_{path_hash}_{page_number}"],
        ]
        command_buttons.append(second_row)

        # Third row
        third_row = []
        # Download button
        if storage_name == octoprint.filemanager.FileDestinations.LOCAL:
            third_row.append([f"{get_emoji('download')} Download", f"{context.cmd}_download_{path_hash}"])
        # Back button
        path_parts = file_path.split("/")
        parent_path = "/".join(path_parts[:-1])
        back_path = f"{storage_name}/{parent_path}" if parent_path else storage_name
        back_path_hash = self.hash_path(back_path)
        third_row.append([f"{get_emoji('back')} Back", f"{context.cmd}_list_{back_path_hash}_{page_number}"])
        # Append
        command_buttons.append(third_row)

        # Send the message
        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def file_details(self, context: CommandContext, path_hash, page_number):
        # Lookup file data and metadata
        try:
            storage_name, file_path = self.find_path_by_hash(path_hash)
            _, filename = self.main._file_manager.split_path(storage_name, file_path)
            file_metadata = self.main._file_manager.get_metadata(storage_name, file_path)
            analysis = file_metadata.get("analysis", {})
            statistics = file_metadata.get("statistics", {})
            history = file_metadata.get("history", {})
        except Exception:
            msg = f"{get_emoji('attention')} I couldn't find the file you were looking for. Perhaps you want to have a look at {context.cmd} again?"
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        # Message header
        msg = f"{get_emoji('info')} <b>File information</b>\n\n"
        msg += f"{get_emoji('name')} <b>Name:</b> <code>{html.escape(filename)}</code>"

        # Upload timestamp
        try:
            lastmodified = self.main._file_manager.get_lastmodified(storage_name, file_path)
            dt = datetime.datetime.fromtimestamp(lastmodified)
            msg += f"\n{get_emoji('calendar')} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            self._logger.exception("Caught an exception getting file date")

        # File size
        filesize = self.main._file_manager.get_size(storage_name, file_path)
        msg += f"\n{get_emoji('filesize')} <b>Size:</b> {Formatters.format_size(filesize)}"

        # Filament info
        filament_length = 0
        try:
            filament = analysis.get("filament", {})
            if filament:
                msg += f"\n{get_emoji('filament')} <b>Filament:</b> "
                if len(filament) == 1 and "length" in filament.get("tool0", {}):
                    msg += Formatters.format_filament(filament["tool0"])
                    filament_length += float(filament["tool0"]["length"])
                else:
                    for tool in sorted(filament):
                        length = filament[tool].get("length")
                        if length is not None:
                            msg += f"\n      {html.escape(tool)}: {Formatters.format_filament(filament[tool])}"
                            filament_length += float(length)
        except Exception:
            self._logger.exception("Caught an exception getting filament info")

        # Print time
        print_time = analysis.get("estimatedPrintTime")
        if print_time:
            msg += f"\n{get_emoji('stopwatch')} <b>Print Time:</b> {Formatters.format_fuzzy_print_time(print_time)}"

            # ETA
            try:
                time_finish = self.main.calculate_ETA(print_time)
                msg += f"\n{get_emoji('finish')} <b>Completed Time:</b> {html.escape(time_finish)}"
            except Exception:
                self._logger.exception("Caught an exception calculating ETA")

            # Cost calculation (if plugin active)
            if self.main._plugin_manager.get_plugin("cost", True) and filament_length:
                try:
                    cp_h = self.main._settings.global_get_float(["plugins", "cost", "cost_per_time"])
                    cp_m = self.main._settings.global_get_float(["plugins", "cost", "cost_per_length"])
                    curr = self.main._settings.global_get(["plugins", "cost", "currency"])
                    cost = filament_length / 1000 * cp_m + print_time / 3600 * cp_h
                    msg += f"\n{get_emoji('cost')} <b>Cost:</b> {html.escape(curr)}{cost:.02f}"
                except Exception:
                    self._logger.exception("Caught an exception calculating cost")

        # Average print times
        try:
            average_print_times = statistics.get("averagePrintTime")
            if average_print_times:
                msg += "\n\n<b>Average Print Time:</b>"
                for profile_id, average_print_time in islice(average_print_times.items(), 5):
                    try:
                        profile = self.main._printer_profile_manager.get(profile_id)
                        msg += (
                            f"\n      {html.escape(profile['name'])}: {Formatters.format_duration(average_print_time)}"
                        )
                    except Exception:
                        self._logger.exception("Error processing average print time for profile '%s'", profile_id)
        except Exception:
            self._logger.exception("Caught an exception retrieving average print times")

        # Last print times
        last_print_times = statistics.get("lastPrintTime")
        if last_print_times:
            msg += "\n\n<b>Last Print Time:</b>"
            for profile_id, last_print_time in islice(last_print_times.items(), 5):
                try:
                    profile = self.main._printer_profile_manager.get(profile_id)
                    msg += f"\n      {html.escape(profile['name'])}: {Formatters.format_duration(last_print_time)}"
                except Exception:
                    self._logger.exception(
                        "Caught an exception processing last print time for profile '%s'", profile_id
                    )

        # Prints history
        if history:
            msg += "\n\n<b>Print History:</b>"
            for history_entry in islice(history, 5):
                try:
                    timestamp = history_entry.get("timestamp")
                    if timestamp:
                        formatted_ts = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                        msg += f"\n      Timestamp: {formatted_ts}"

                    print_time = history_entry.get("printTime")
                    if print_time is not None:
                        msg += f"\n      Print Time: {Formatters.format_duration(print_time)}"

                    profile_id = history_entry.get("printerProfile")
                    if profile_id:
                        try:
                            profile = self.main._printer_profile_manager.get(profile_id)
                            msg += f"\n      Printer Profile: {html.escape(profile['name'])}"
                        except Exception:
                            self._logger.exception("Failed to get printer profile '%s'", profile_id)

                    success = history_entry.get("success")
                    if success is not None:
                        msg += "\n      Successfully printed" if success else "\n      Print failed"

                    msg += "\n"
                except Exception:
                    self._logger.exception("Caught an exception processing history")

        # Upload the thumbnail image to imgbb to get a public URL
        imgbb_thumbnail_url = self.upload_thumbnail_to_imgbb(file_metadata)
        if imgbb_thumbnail_url:
            msg = f"<a href='{imgbb_thumbnail_url}'>&#8199;</a>\n{msg}"

        # Create command buttons
        command_buttons = [
            [
                [
                    f"{get_emoji('back')} Back",
                    f"{context.cmd}_info_{path_hash}_{page_number}",
                ]
            ]
        ]

        # Send the message
        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def file_settings(self, context: CommandContext, path_hash, page_number, selection):
        if selection in ("name", "date"):
            sort_by_date = selection == "date"
            self.main._settings.set_boolean(["sort_files_by_date"], sort_by_date)
            self.main._settings.save()
            self.file_list(context, path_hash, page_number)
            return

        msg = f"{get_emoji('question')} <b>Choose sorting order of files</b>"

        command_buttons = [
            [
                [
                    f"{get_emoji('name')} By name",
                    f"{context.cmd}_settings_{path_hash}_{page_number}_name",
                ],
                [
                    f"{get_emoji('calendar')} By date",
                    f"{context.cmd}_settings_{path_hash}_{page_number}_date",
                ],
            ],
            [
                [
                    f"{get_emoji('back')} Back",
                    f"{context.cmd}_list_{path_hash}_{page_number}",
                ]
            ],
        ]

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def file_copy_move(self, context: CommandContext, from_hash, page_number, to_hash, confirmation, operation):
        try:
            if context.msg_id_to_update:
                self.main.send_msg(
                    f"{get_emoji('loading')} Loading files...",
                    chatID=context.chat_id,
                    msg_id=context.msg_id_to_update,
                )
            else:
                loading_files_response = self.main.telegram_utils.send_telegram_request(
                    f"{self.main.bot_url}/sendMessage",
                    "post",
                    data={
                        "text": f"{get_emoji('loading')} Loading files...",
                        "chat_id": context.chat_id,
                    },
                )
                context.msg_id_to_update = loading_files_response["result"]["message_id"]
        except Exception:
            pass

        if operation not in ("copy", "move"):
            raise RuntimeError("Unknown operation")

        try:
            from_storage_name, from_path = self.find_path_by_hash(from_hash)
            full_from_file_path_to_display = f"/{from_storage_name}/{from_path}"
        except Exception:
            msg = f"{get_emoji('attention')} The file you chose no longer exists. Perhaps you want to have a look at {context.cmd} again?"
            self.main.send_msg(msg, chatID=context.chat_id, msg_id=context.msg_id_to_update)
            return

        if to_hash and confirmation == "a":  # Ask for confirmation
            try:
                to_storage_name, to_path = self.find_path_by_hash(to_hash)
                full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")
            except Exception:
                msg = f"{get_emoji('attention')} The destination path you chose is unavailable. Perhaps you want to have a look at {context.cmd} again?"
                self.main.send_msg(msg, chatID=context.chat_id, msg_id=context.msg_id_to_update)
                return

            command_buttons = [
                [
                    [
                        f"{get_emoji('check')} Yes",
                        f"{context.cmd}_{operation}_{from_hash}_{page_number}_{to_hash}_y",
                    ],
                    [
                        f"{get_emoji('cancel')} No",
                        f"{context.cmd}_{operation}_{from_hash}_{page_number}_{to_hash}",
                    ],
                ]
            ]

            self.main.send_msg(
                f"{get_emoji('warning')} {operation.capitalize()} <code>{html.escape(full_from_file_path_to_display)}</code> to <code>{html.escape(full_to_file_path_to_display)}</code>?",
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )
        elif to_hash and confirmation == "y":  # Run the copy/move
            # Copy/move code is adapted from the filemanager plugin: https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
            try:
                to_storage_name, to_path = self.find_path_by_hash(to_hash)
                full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")
            except Exception:
                msg = f"{get_emoji('attention')} The destination path you chose is unavailable. Perhaps you want to have a look at {context.cmd} again?"
                self.main.send_msg(msg, chatID=context.chat_id, msg_id=context.msg_id_to_update)
                return

            failure_reason = None
            try:
                from octoprint.server.api.files import (
                    _getCurrentFile,
                    _isBusy,
                    _verifyFileExists,
                    _verifyFolderExists,
                )

                if not _verifyFileExists(from_storage_name, from_path):
                    failure_reason = "Source does not exist or isn't a file"
                elif not _verifyFolderExists(to_storage_name, to_path):
                    failure_reason = "Destination doesn't exist or it isn't a folder"
                else:
                    _, from_filename = self.main._file_manager.split_path(from_storage_name, from_path)
                    final_to_path = self.main._file_manager.join_path(to_storage_name, to_path, from_filename)

                    if _verifyFileExists(to_storage_name, final_to_path) or _verifyFolderExists(
                        to_storage_name, final_to_path
                    ):
                        failure_reason = "Destination already exists"
                    else:
                        if operation == "copy":
                            # Copy the file
                            self.main._file_manager.copy_file(to_storage_name, from_path, final_to_path)
                        elif operation == "move":
                            if _isBusy(from_storage_name, from_path):
                                failure_reason = "Source is currently in use"

                            # Deselect source file if currently selected
                            _, currentFilename = _getCurrentFile()
                            if currentFilename == from_path:
                                self.main._printer.unselect_file()

                            # Move the file
                            self.main._file_manager.move_file(to_storage_name, from_path, final_to_path)
                        else:
                            failure_reason = "Unknown operation"

            except Exception:
                self._logger.exception("Caught an exception copying/moving file %s", full_to_file_path_to_display)
                failure_reason = "Internal error, please check logs"

            if failure_reason:
                msg = (
                    f"{get_emoji('attention')} Cannot {operation} file <code>{html.escape(full_from_file_path_to_display)}</code> to <code>{html.escape(full_to_file_path_to_display)}</code>"
                    f"\nReason: {failure_reason}"
                )

                command_buttons = [
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{context.cmd}_list_{from_hash}_{page_number}",
                        ]
                    ]
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
            else:
                if operation == "copy":
                    action_done = "copied"
                elif operation == "move":
                    action_done = "moved"

                msg = f"{get_emoji('check')} File <code>{html.escape(full_from_file_path_to_display)}</code> {action_done} to <code>{html.escape(full_to_file_path_to_display)}</code>"

                back_path = f"{to_storage_name}/{to_path}" if to_path else to_storage_name
                parent_folder_hash = self.hash_path(back_path)
                command_buttons = [
                    [
                        [
                            f"{get_emoji('back')} Back",
                            f"{context.cmd}_list_{parent_folder_hash}_{page_number}",
                        ]
                    ]
                ]

                self.main.send_msg(
                    msg,
                    chatID=context.chat_id,
                    markup="HTML",
                    responses=command_buttons,
                    msg_id=context.msg_id_to_update,
                )
        else:  # Navigate folders
            storages = self.list_files(recursive=False)

            msg = f"{get_emoji('question')} Where do you want to {operation} the file <code>{html.escape(full_from_file_path_to_display)}</code>?"

            command_buttons = []

            if to_hash:  # Start navigation from target_path
                try:
                    to_storage_name, to_path = self.find_path_by_hash(to_hash)
                    full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")

                    msg += f"\nCurrent selection: <code>{html.escape(full_to_file_path_to_display)}</code>"

                    # Up button
                    if to_path:
                        to_path_parts = [to_storage_name] + to_path.split("/")
                        parent_folder_path = "/".join(to_path_parts[:-1])
                        parent_folder_hash = self.hash_path(parent_folder_path)
                        command_buttons.append(
                            [
                                [
                                    f"{get_emoji('up')} Parent",
                                    f"{context.cmd}_{operation}_{from_hash}_{page_number}_{parent_folder_hash}",
                                ]
                            ]
                        )
                    elif len(storages) > 1:
                        command_buttons.append(
                            [
                                [
                                    f"{get_emoji('up')} Parent",
                                    f"{context.cmd}_{operation}_{from_hash}_{page_number}",
                                ]
                            ]
                        )

                    # Folder buttons
                    to_path_listing = self.list_files(
                        locations=to_storage_name,
                        path=to_path,
                        filter=lambda node: node["type"] == "folder",
                        recursive=False,
                    )
                    to_path_folders = to_path_listing.get(to_storage_name, {})
                    for folder_name in sorted(to_path_folders):
                        folder_path = "/".join(filter(None, [to_storage_name, to_path, folder_name]))
                        folder_hash = self.hash_path(folder_path)
                        command_buttons.append(
                            [
                                [
                                    f"{get_emoji('folder')} {folder_name}",
                                    f"{context.cmd}_{operation}_{from_hash}_{page_number}_{folder_hash}",
                                ]
                            ]
                        )

                    # Copy/Move here button
                    command_buttons.append(
                        [
                            [
                                f"{get_emoji('check')} {operation.capitalize()} here",
                                f"{context.cmd}_{operation}_{from_hash}_{page_number}_{to_hash}_a",
                            ]
                        ]
                    )
                except Exception:
                    msg = f"{get_emoji('attention')} The path you were browsing no longer exists. Perhaps you want to have a look at {context.cmd} again?"
                    self.main.send_msg(msg, chatID=context.chat_id, msg_id=context.msg_id_to_update)
                    return
            else:  # Select storage
                if len(storages) == 1:
                    storage_name = next(iter(storages))
                    storage_hash = self.hash_path(storage_name)
                    self.file_copy_move(context, from_hash, page_number, storage_hash, confirmation, operation)
                    return

                for storage_name in storages:
                    storage_hash = self.hash_path(storage_name)
                    command_buttons.append(
                        [[storage_name, f"{context.cmd}_{operation}_{from_hash}_{page_number}_{storage_hash}"]]
                    )

            # Back button
            command_buttons.append([[f"{get_emoji('back')} Back", f"{context.cmd}_info_{from_hash}_{page_number}"]])

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def file_print(self, context: CommandContext, path_hash, page_number):
        if not self.main.is_command_allowed(context.chat_id, context.from_id, "/print"):
            msg = f"{get_emoji('notallowed')} You are not allowed to print!"
            command_buttons = [
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"{context.cmd}_info_{path_hash}_{page_number}",
                    ],
                ]
            ]
            self.main.send_msg(
                msg,
                responses=command_buttons,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        if not self.main._printer.is_ready():
            msg = f"{get_emoji('warning')} Can't start a new print, printer is not ready. Printer status: {self.main._printer.get_state_string()}."
            command_buttons = [
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"{context.cmd}_info_{path_hash}_{page_number}",
                    ],
                ]
            ]
            self.main.send_msg(
                msg,
                responses=command_buttons,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        try:
            destination, file = self.find_path_by_hash(path_hash)

            if destination == octoprint.filemanager.FileDestinations.SDCARD:
                self.main._printer.select_file(file, True, printAfterSelect=False)
            else:
                file = self.main._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, file)
                self.main._printer.select_file(file, False, printAfterSelect=False)
        except Exception:
            msg = f"{get_emoji('attention')} I couldn't find the file you wanted to print. Perhaps you want to have a look at {context.cmd} again?"
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                msg_id=context.msg_id_to_update,
            )
            return

        current_data = self.main._printer.get_current_data()
        job_file_name = current_data.get("job", {}).get("file", {}).get("name", "")

        msg = (
            f"{get_emoji('info')} The file <code>{html.escape(job_file_name)}</code> is loaded.\n\n"
            f"{get_emoji('question')} Do you want to start printing it now?"
        )

        command_buttons = [
            [
                [
                    f"{get_emoji('play')} Print",
                    "/print_y",
                ],
                [
                    f"{get_emoji('back')} Back",
                    f"{context.cmd}_info_{path_hash}_{page_number}",
                ],
            ]
        ]

        self.main.send_msg(
            msg,
            chatID=context.chat_id,
            markup="HTML",
            responses=command_buttons,
            msg_id=context.msg_id_to_update,
        )

    def file_download(self, context: CommandContext, path_hash):
        try:
            storage_name, file_path = self.find_path_by_hash(path_hash)
            file_path_on_disk = self.main._file_manager.path_on_disk(storage_name, file_path)
            self.main.send_file(context.chat_id, file_path_on_disk)
        except Exception:
            msg = f"{get_emoji('attention')} I couldn't find the file you were looking for. Perhaps you want to have a look at {context.cmd} again?"
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
            )

    def file_delete(self, context: CommandContext, path_hash, page_number, confirm):
        try:
            storage_name, file_path = self.find_path_by_hash(path_hash)
            full_file_path_to_display = f"/{storage_name}/{file_path}"
        except Exception:
            msg = f"{get_emoji('attention')} I couldn't find the file you were looking for. Perhaps you want to have a look at {context.cmd} again?"
            self.main.send_msg(
                msg,
                chatID=context.chat_id,
            )
            return

        if confirm == "yes":
            # Deletion code is adapted from the filemanager plugin: https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
            failure_reason = None
            try:
                from octoprint.server.api.files import (
                    _getCurrentFile,
                    _isBusy,
                    _verifyFileExists,
                )

                if not _verifyFileExists(storage_name, file_path):
                    failure_reason = "File doesn't exist or isn't a file"
                elif _isBusy(storage_name, file_path):
                    failure_reason = "File is currently in use"
                else:
                    # Deselect file if currently selected
                    _, currentFilename = _getCurrentFile()
                    if currentFilename == file_path:
                        self.main._printer.unselect_file()

                    # Delete the file
                    if storage_name == octoprint.filemanager.FileDestinations.SDCARD:
                        self.main._printer.delete_sd_file(file_path)
                    else:
                        self.main._file_manager.remove_file(storage_name, file_path)
            except Exception:
                self._logger.exception("Caught an exception deleting file %s", file_path)
                failure_reason = "Internal error, please check logs"

            if failure_reason:
                msg = (
                    f"{get_emoji('attention')} Cannot delete <code>{html.escape(full_file_path_to_display)}</code>!\n"
                    f"Reason: {failure_reason}"
                )
            else:
                msg = f"{get_emoji('check')} File <code>{html.escape(full_file_path_to_display)}</code> deleted!"

            path_parts = file_path.split("/")
            parent_path = "/".join(path_parts[:-1])
            back_path = f"{storage_name}/{parent_path}" if parent_path else storage_name
            back_path_hash = self.hash_path(back_path)
            command_buttons = [
                [
                    [
                        f"{get_emoji('back')} Back",
                        f"{context.cmd}_list_{back_path_hash}_{page_number}",
                    ]
                ]
            ]

            self.main.send_msg(
                msg,
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )
        else:
            command_buttons = [
                [
                    [
                        f"{get_emoji('check')} Yes",
                        f"{context.cmd}_delete_{path_hash}_{page_number}_yes",
                    ],
                    [
                        f"{get_emoji('cancel')} No",
                        f"{context.cmd}_info_{path_hash}_{page_number}",
                    ],
                ]
            ]
            self.main.send_msg(
                f"{get_emoji('warning')} Delete <code>{html.escape(full_file_path_to_display)}</code>?",
                chatID=context.chat_id,
                markup="HTML",
                responses=command_buttons,
                msg_id=context.msg_id_to_update,
            )

    def update_files_hash_path_map(self, file_listing, locations=None, path=None):
        """
        Updates the internal hash-to-path mapping for OctoPrint files and folders.

        This method creates a mapping between short hash keys and full file/folder paths
        to overcome Telegram's 64-byte callback query data limitation. Each path gets
        a unique 20-character hash that can be used in Telegram inline keyboard callbacks.

        Args:
            file_listing (dict): Dictionary returned by OctoPrint's FileManager.list_files()
            locations (str or list, optional): Storage location(s) that were passed to list_files().
                Can be a single storage name (e.g., "local") or a list of storage names.
            path (str, optional): Folder path that was passed to list_files().
                Represents the folder within the storage location (e.g., "models/prints").

        Examples:
            Update for all storages:
            >>> file_listing = self.main._file_manager.list_files()
            >>> self.update_files_hash_path_map(file_listing)

            Update for specific storage:
            >>> file_listing = self.main._file_manager.list_files(locations="local")
            >>> self.update_files_hash_path_map(file_listing, locations="local")

            Update for specific folder:
            >>> file_listing = self.main._file_manager.list_files(
            ...     locations="local", path="models/prints"
            ... )
            >>> self.update_files_hash_path_map(file_listing, locations="local", path="models/prints")
        """

        def _process_tree(tree, current_path=""):
            for node_name, node_data in tree.items():
                is_folder = node_data.get("type") == "folder"
                full_node_path = f"{current_path}{node_name}"

                path_hash = self.hash_path(full_node_path)
                self.files_hash_path_map[path_hash] = full_node_path

                if is_folder and "children" in node_data:
                    _process_tree(node_data["children"], f"{full_node_path}/")

        if isinstance(locations, str):
            locations = [locations]

        if not locations:
            # Process all storage locations
            for storage_name, storage_tree in file_listing.items():
                path_hash = self.hash_path(storage_name)
                self.files_hash_path_map[path_hash] = storage_name

                _process_tree(storage_tree, f"{storage_name}/")
        else:
            # Process specific location(s)
            for location in locations:
                if location in file_listing:
                    full_path = f"{location}/{path}" if path else location

                    path_hash = self.hash_path(full_path)
                    self.files_hash_path_map[path_hash] = full_path

                    _process_tree(file_listing[location], f"{full_path}/")
                else:
                    self._logger.warning("Parameter mismatch: location %s not found in file listing", location)

    def list_files(self, locations=None, path=None, filter=None, recursive=True, level=0, force_refresh=False):
        """
        List files from OctoPrint and update internal hash-to-path map.
        """

        # List files
        file_listing = self.main._file_manager.list_files(
            locations=locations, path=path, filter=filter, recursive=recursive, level=level, force_refresh=force_refresh
        )

        # Update the file hash path map with the files currently listed, as they may have changed
        self.update_files_hash_path_map(file_listing, locations, path)

        # Return file listing
        return file_listing

    def find_path_by_hash(self, path_hash):
        if path_hash not in self.files_hash_path_map:
            raise Exception("File not found")

        path_with_storage = self.files_hash_path_map[path_hash]  # e.g.: local or local/foo
        path_parts = path_with_storage.split("/")
        storage_name = path_parts[0]  # e.g.: local
        path_without_storage = "/".join(path_parts[1:])  # e.g.: '' or foo
        return storage_name, path_without_storage

    def hash_path(self, path):
        return hashlib.md5(path.encode()).hexdigest()[0 : self.HASH_PATH_LENGTH]

    def upload_thumbnail_to_imgbb(self, file_metadata):
        """
        Upload thumbnail to imgbb and return public URL.

        Args:
            file_metadata (dict): Value returned by octoprint.filemanager.storage.StorageInterface.get_metadata().

        Returns:
            str or None: Public URL of uploaded thumbnail or None if failed.
        """
        try:
            api_key = self.main._settings.get(["imgbbApiKey"])
            upload_url = "https://api.imgbb.com/1/upload"

            if not api_key or not isinstance(file_metadata, dict):
                return

            thumbnail_path = file_metadata.get("thumbnail")
            if not thumbnail_path:
                return

            self._logger.info("Get thumbnail: %s", thumbnail_path)

            thumbnail_response = self.main.send_octoprint_request(f"/{thumbnail_path}")
            if not thumbnail_response.ok:
                return

            self._logger.info("Uploading thumbnail to imgbb: %s", thumbnail_path)

            encoded_img = base64.b64encode(thumbnail_response.content)
            payload = {"key": api_key, "image": encoded_img}

            upload_response = requests.post(upload_url, payload)
            if not upload_response.ok:
                return

            return upload_response.json()["data"]["url"]
        except Exception:
            self._logger.exception("Caught an exception uploading thumbnail to imgbb")
