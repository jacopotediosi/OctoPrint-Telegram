from __future__ import annotations

import base64
import datetime
import html
import os
from itertools import islice

import octoprint.filemanager
import requests
from typing_extensions import override

from ..domain import permissions
from ..emoji import Emoji
from ..telegram import Markup, MenuState, StaleMenuError
from ..utils import Formatters
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class FilesMenuState(MenuState):
    """The entries the menu offers and the operation being carried out on one of them."""

    def __init__(
        self,
        folder: str = "",
        page: int = 0,
        items: list[str] | None = None,
        selected: str | None = None,
        operation: str | None = None,
        target: str | None = None,
        slicer: str | None = None,
        slicer_profile: str | None = None,
        printer_profile: str | None = None,
    ) -> None:
        """Set up the entries the menu offers and the operation being carried out on one of them.

        Args:
            folder (str, optional): The folder being browsed, its storage included.
            page (int, optional): The page of the folder being shown.
            items (list[str], optional): The path of each entry the menu offers, their storage included.
            selected (str, optional): The path the operation acts on, its storage included.
            operation (str, optional): Either "copy" or "move".
            target (str, optional): The folder to copy or move to, its storage included.
            slicer (str, optional): The id of the slicer picked so far.
            slicer_profile (str, optional): The id of the slicing profile picked so far.
            printer_profile (str, optional): The id of the printer profile picked so far.
        """
        self.folder = folder
        self.page = page
        self.items = items or []
        self.selected = selected
        self.operation = operation
        self.target = target
        self.slicer = slicer
        self.slicer_profile = slicer_profile
        self.printer_profile = printer_profile


class CmdFiles(BaseCommand):
    # Number of items (folders + files) to display per page
    PAGE_SIZE = 14

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Browse and manage files.

        The callback query carries the action and, when the action is about one of the entries on
        screen, the position of that entry. The paths themselves travel in the menu state.

        Possible callback queries, where {position} stands for the position of an entry:

        Browsing:
        - /files -> show the storage menu, or the root of the only storage there is
        - /files_list_{position} -> open the folder at that position
        - /files_list -> show the folder being browsed, at the page it was left on
        - /files_up -> open the parent of the folder being browsed
        - /files_prevpage -> show the previous page of the folder being browsed
        - /files_nextpage -> show the next page of the folder being browsed

        File information:
        - /files_info_{position} -> select the file at that position and show its information
        - /files_info -> show the information of the selected file
        - /files_details -> show the details of the selected file

        Browsing settings:
        - /files_settings -> ask which browsing setting to change
        - /files_settings_sort -> ask how to sort files
        - /files_settings_sort_byname -> sort files by name
        - /files_settings_sort_bydate -> sort files by date
        - /files_settings_models -> ask whether to list models
        - /files_settings_models_show -> also list models
        - /files_settings_models_hide -> list printable files only

        Operations on the selected file:
        - /files_download -> send the selected file to the chat
        - /files_selectforprint -> select the file for printing
        - /files_delete -> ask whether to delete the selected file
        - /files_delete_yes -> delete the selected file
        - /files_copy -> start choosing the folder to copy the selected file to
        - /files_move -> start choosing the folder to move the selected file to
        - /files_copymove_{position} -> open the folder at that position while choosing the destination
        - /files_copymove_up -> open the parent of the destination being browsed
        - /files_copymove_here -> ask whether to copy or move the selected file to the destination being browsed
        - /files_copymove_yes -> copy or move the selected file to the destination being browsed

        Slicing:
        - /files_slice -> ask for the slicer, the slicing profile and the printer profile, one at a time,
          skipping every choice that has a single option
        - /files_slice_slicer -> go back to the slicer choice, and forget the slicing and printer profiles
        - /files_slice_slicerprofile -> go back to the slicing profile choice, and forget the printer profile
        - /files_slice_printerprofile -> go back to the printer profile choice
        - /files_slice_{position} -> pick the option at that position for the choice being asked
        - /files_slice_confirm -> slice the selected model with the choices made
        """
        if not command_context.parameter:
            self._file_list(command_context, FilesMenuState())
            return

        action, _, argument = command_context.parameter.partition("_")

        menu_state = self.require_menu_state(command_context, FilesMenuState)

        if action == "list":
            if argument:
                menu_state.folder = self._chosen_item(menu_state, argument)
                menu_state.page = 0
            self._file_list(command_context, menu_state)

        elif action == "up":
            menu_state.folder = "/".join(menu_state.folder.split("/")[:-1])
            menu_state.page = 0
            self._file_list(command_context, menu_state)

        elif action in ("prevpage", "nextpage"):
            menu_state.page += -1 if action == "prevpage" else 1
            self._file_list(command_context, menu_state)

        elif action == "info":
            if argument:
                menu_state.selected = self._chosen_item(menu_state, argument)
            self._file_info(command_context, menu_state)

        elif action == "details":
            self._file_details(command_context, menu_state)

        elif action == "settings":
            setting, _, value = argument.partition("_")
            if setting == "sort":
                self._file_sort_setting(command_context, menu_state, value == "bydate" if value else None)
            elif setting == "models":
                self._file_models_setting(command_context, menu_state, value == "show" if value else None)
            else:
                self._file_settings(command_context, menu_state)

        elif action == "download":
            self._file_download(command_context, menu_state)

        elif action == "delete":
            if argument == "yes":
                self._file_delete(command_context, menu_state)
            else:
                self._file_delete_confirmation(command_context, menu_state)

        elif action in ("copy", "move"):
            menu_state.operation = action
            menu_state.target = None
            self._file_copy_move_destination(command_context, menu_state)

        elif action == "copymove":
            if argument == "here":
                self._file_copy_move_confirmation(command_context, menu_state)
            elif argument == "yes":
                self._file_copy_move(command_context, menu_state)
            else:
                if argument == "up":
                    menu_state.target = "/".join((menu_state.target or "").split("/")[:-1]) or None
                elif argument:
                    menu_state.target = self._chosen_item(menu_state, argument)
                self._file_copy_move_destination(command_context, menu_state)

        elif action == "selectforprint":
            self._file_print(command_context, menu_state)

        elif action == "slice":
            if not argument:
                self._clear_slice_choices_from(menu_state, "slicer")
            elif argument.isdigit():
                self._pick_slice_option(menu_state, self._chosen_item(menu_state, argument))
            elif argument in ("slicer", "slicerprofile", "printerprofile"):
                self._clear_slice_choices_from(menu_state, argument)
            self._file_slice(command_context, menu_state, confirmed=argument == "confirm")

    def _chosen_item(self, menu_state: FilesMenuState, position: str) -> str:
        """Return the path of the entry the user picked.

        Args:
            menu_state (FilesMenuState): The state of the menu the entry was picked from.
            position (str): The position the button carries.

        Returns:
            str: The path of the entry, its storage included.

        Raises:
            StaleMenuError: If the menu offers no entry at that position.
        """
        if not position.isdigit() or int(position) >= len(menu_state.items):
            raise StaleMenuError
        return menu_state.items[int(position)]

    def _split_storage_and_path(self, path_with_storage: str) -> tuple[str, str]:
        """Return the storage a path is in and the path inside it.

        Args:
            path_with_storage (str): The path, its storage included.

        Returns:
            tuple[str, str]: The name of the storage, then the path inside it.
        """
        storage_name, _, path_without_storage = path_with_storage.partition("/")
        return storage_name, path_without_storage

    def _selected_storage_and_path(self, menu_state: FilesMenuState) -> tuple[str, str]:
        """Return the storage the selected file is in and its path inside it.

        Args:
            menu_state (FilesMenuState): The state of the menu the file was selected from.

        Returns:
            tuple[str, str]: The name of the storage, then the path inside it.

        Raises:
            StaleMenuError: If the menu carries no selected file.
        """
        if not menu_state.selected:
            raise StaleMenuError
        return self._split_storage_and_path(menu_state.selected)

    def _file_list(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        sent_message_id = self.plugin_context.sender.send_message(
            render_emojis("{emo:loading} Loading files..."),
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
        if sent_message_id:
            command_context.msg_id_to_update = sent_message_id

        if not menu_state.folder:  # Show storage selection
            storages = self.plugin_context.file_manager.list_files(recursive=False)

            if len(storages) == 1:
                menu_state.folder = next(iter(storages))
                self._file_list(command_context, menu_state)
            elif len(storages) > 1:
                msg = render_emojis("{emo:save} <b>Select Storage</b>")

                menu_state.items = list(storages)

                command_buttons = [
                    [
                        (
                            render_emojis(f"{{emo:folder}} {storage_name}"),
                            f"{command_context.cmd}_list_{storage_position}",
                        )
                    ]
                    for storage_position, storage_name in enumerate(menu_state.items)
                ]
                command_buttons.append([(render_emojis("{emo:cancel} Close"), "close")])

                self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

        else:  # List files in path
            path_with_storage = menu_state.folder  # e.g.: local or local/foo
            path_parts = path_with_storage.split("/")
            storage_name = path_parts[0]  # e.g.: local
            path_without_storage = "/".join(path_parts[1:])  # e.g.: '' or foo
            path_is_storage_root = len(path_parts) < 2

            try:
                file_listing = self.plugin_context.file_manager.list_files(
                    locations=storage_name, path=path_without_storage, recursive=False
                )
            except Exception:
                msg = render_emojis(
                    f"{{emo:attention}} The path you were browsing no longer exists. Perhaps you want to have a look at {command_context.cmd} again?"
                )
                self.update_menu(command_context, msg, None)
                return

            path_content = file_listing.get(storage_name, {})

            # --- Calculate pagination ---
            folders = {name: data for name, data in path_content.items() if data.get("type") == "folder"}

            file_types_to_show = (
                ("machinecode", "model") if self.plugin_context.settings.show_models_in_files else ("machinecode",)
            )
            files = {name: data for name, data in path_content.items() if data.get("type") in file_types_to_show}

            total_folders = len(folders)
            total_files = len(files)
            total_items = total_folders + total_files
            total_pages = max(1, (total_items + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

            menu_state.page = max(0, min(menu_state.page, total_pages - 1))
            start_index = menu_state.page * self.PAGE_SIZE
            end_index = start_index + self.PAGE_SIZE

            menu_state.items = []

            # --- Create folder buttons (paginated) ---
            sorted_folder_names = sorted(folders.keys())
            paginated_folder_names = sorted_folder_names[start_index : min(len(sorted_folder_names), end_index)]

            folder_buttons = []
            for folder_name in paginated_folder_names:
                menu_state.items.append(f"{path_with_storage}/{folder_name}")
                folder_buttons.append(
                    (
                        render_emojis(f"{{emo:folder}} {folder_name}"),
                        f"{command_context.cmd}_list_{len(menu_state.items) - 1}",
                    )
                )

            # --- Create file buttons (paginated) ---
            # Calculate remaining slots for files after folders
            remaining_slots = end_index - len(paginated_folder_names) - start_index

            file_buttons = []
            if remaining_slots > 0:
                remaining_start = max(0, start_index - len(sorted_folder_names))

                # Sort files
                if self.plugin_context.settings.sort_files_by_date:
                    sorted_files = sorted(files.items(), key=lambda x: x[1].get("date", 0), reverse=True)
                else:
                    sorted_files = sorted(files.items())

                # Get only the files for current page
                paginated_files = sorted_files[remaining_start : remaining_start + remaining_slots]

                # Create buttons only for paginated files
                for filename, file_data in paginated_files:
                    file_base_name = filename.rsplit(".", 1)[0]
                    if file_data.get("type") == "model":
                        display_filename = render_emojis(f"{{emo:model}} {file_base_name}")
                    else:
                        try:
                            if "history" not in file_data:
                                display_filename = render_emojis(f"{{emo:new}} {file_base_name}")
                            else:
                                history_list = file_data["history"]
                                if not history_list:
                                    display_filename = render_emojis(f"{{emo:file}} {file_base_name}")
                                else:
                                    history_list.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                                    latest_history = history_list[0]

                                    if latest_history.get("success"):
                                        display_filename = render_emojis(f"{{emo:hooray}} {file_base_name}")
                                    else:
                                        display_filename = render_emojis(f"{{emo:warning}} {file_base_name}")
                        except Exception:
                            self._logger.exception("Error processing history for file '%s'", filename)
                            display_filename = render_emojis(f"{{emo:file}} {file_base_name}")

                    menu_state.items.append(f"{path_with_storage}/{filename}")
                    command = f"{command_context.cmd}_info_{len(menu_state.items) - 1}"
                    file_buttons.append((display_filename, command))

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
                nav_and_actions_row.append(
                    (
                        render_emojis("{emo:back} Back"),
                        f"{command_context.cmd}_up",
                    )
                )

            # Prev/next page
            if total_pages > 1:
                if menu_state.page > 0:
                    nav_and_actions_row.append(
                        (
                            render_emojis("{emo:up} Prev page"),
                            f"{command_context.cmd}_prevpage",
                        )
                    )
                if menu_state.page + 1 < total_pages:
                    nav_and_actions_row.append(
                        (
                            render_emojis("{emo:down} Next page"),
                            f"{command_context.cmd}_nextpage",
                        )
                    )

            # Settings and close
            nav_and_actions_row.extend(
                [
                    (
                        render_emojis("{emo:settings} Settings"),
                        f"{command_context.cmd}_settings",
                    ),
                    (
                        render_emojis("{emo:cancel} Close"),
                        "close",
                    ),
                ]
            )

            command_buttons.append(nav_and_actions_row)

            # --- Create message ---
            page_str = f"    [{menu_state.page + 1} / {total_pages}]" if total_pages > 1 else ""
            msg = render_emojis(f"{{emo:save}} Files in <code>/{html.escape(path_with_storage)}</code>{page_str}")

            # --- Send message ---
            self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_info(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._selected_storage_and_path(menu_state)

        # Lookup file data and metadata
        try:
            _, filename = self.plugin_context.file_manager.split_path(storage_name, file_path)
            file_metadata = self.plugin_context.file_manager.get_metadata(storage_name, file_path) or {}
            analysis = file_metadata.get("analysis") or {}
            history = file_metadata.get("history") or []
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you were looking for. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.update_menu(command_context, msg, None)
            return

        # Message header
        msg = render_emojis(
            f"{{emo:info}} <b>File information</b>\n\n{{emo:name}} <b>Name:</b> <code>{html.escape(filename)}</code>"
        )

        # Upload timestamp
        try:
            lastmodified = self.plugin_context.file_manager.get_lastmodified(storage_name, file_path)
            if lastmodified is not None:
                dt = datetime.datetime.fromtimestamp(lastmodified).astimezone()
                msg += render_emojis(f"\n{{emo:calendar}} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            self._logger.exception("Caught an exception getting file date")

        # Print history
        if "model" not in octoprint.filemanager.get_file_type(filename):
            if not history:
                msg += render_emojis("\n{emo:new} <b>Number of Print:</b> 0")
            else:
                try:
                    history.sort(key=lambda x: x["timestamp"], reverse=True)
                    success = history[0].get("success", False)
                    icon_name = "hooray" if success else "warning"
                except Exception:
                    self._logger.exception("Caught an exception reading history list")
                    icon_name = "file"
                msg += render_emojis(f"\n{{emo:{icon_name}}} <b>Number of Print:</b> {len(history)}")

        # File size
        filesize = self.plugin_context.file_manager.get_size(storage_name, file_path)
        msg += render_emojis(f"\n{{emo:filesize}} <b>Size:</b> {Formatters.format_size(filesize)}")

        # Dimensions
        dimensions = analysis.get("dimensions", {})
        dimension_parts = []
        if "width" in dimensions:
            dimension_parts.append("{:.2f}mm (X)".format(dimensions["width"]))
        if "depth" in dimensions:
            dimension_parts.append("{:.2f}mm (Y)".format(dimensions["depth"]))
        if "height" in dimensions:
            dimension_parts.append("{:.2f}mm (Z)".format(dimensions["height"]))
        if dimension_parts:
            msg += render_emojis("\n{emo:dimensions} <b>Dimensions:</b> ") + " &#215; ".join(dimension_parts)

        # Filament info
        filament_length = 0
        try:
            filament = analysis.get("filament", {})
            if filament:
                msg += render_emojis("\n{emo:filament} <b>Filament:</b> ")
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
            msg += render_emojis(
                f"\n{{emo:stopwatch}} <b>Print Time:</b> {Formatters.format_fuzzy_print_time(print_time)}"
            )

            # ETA
            try:
                time_finish = Formatters.format_eta(self.plugin_context.settings, print_time)
                msg += render_emojis(f"\n{{emo:finish}} <b>Completed Time:</b> {html.escape(time_finish)}")
            except Exception:
                self._logger.exception("Caught an exception calculating ETA")

            # Cost calculation (if plugin active)
            if self.plugin_context.plugins.is_enabled("cost") and filament_length:
                try:
                    cp_h = self.plugin_context.cost.cost_per_time
                    cp_m = self.plugin_context.cost.cost_per_length
                    curr = self.plugin_context.cost.currency
                    cost = filament_length / 1000 * cp_m + print_time / 3600 * cp_h
                    msg += render_emojis(f"\n{{emo:cost}} <b>Cost:</b> {html.escape(curr)}{cost:.02f}")
                except Exception:
                    self._logger.exception("Caught an exception calculating cost")

        # Upload the thumbnail image to imgbb to get a public URL
        imgbb_thumbnail_url = self._upload_thumbnail_to_imgbb(storage_name, file_path)
        if imgbb_thumbnail_url:
            msg = f"<a href='{imgbb_thumbnail_url}'>&#8199;</a>\n{msg}"

        # Create command buttons
        command_buttons = []

        # First row
        if "model" in octoprint.filemanager.get_file_type(filename):
            # Slice
            first_row = [
                (render_emojis("{emo:slice} Slice"), f"{command_context.cmd}_slice"),
            ]
        else:
            # Print + Details
            first_row = [
                (render_emojis("{emo:play} Print"), f"{command_context.cmd}_selectforprint"),
                (render_emojis("{emo:search} Details"), f"{command_context.cmd}_details"),
            ]
        command_buttons.append(first_row)

        # Second row: File ops
        second_row = [
            (render_emojis("{emo:cut} Move"), f"{command_context.cmd}_move"),
            (render_emojis("{emo:copy} Copy"), f"{command_context.cmd}_copy"),
            (render_emojis("{emo:delete} Delete"), f"{command_context.cmd}_delete"),
        ]
        command_buttons.append(second_row)

        # Third row
        third_row = []
        # Download button
        if storage_name == octoprint.filemanager.FileDestinations.LOCAL:
            third_row.append((render_emojis("{emo:download} Download"), f"{command_context.cmd}_download"))
        # Back button
        third_row.append((render_emojis("{emo:back} Back"), f"{command_context.cmd}_list"))
        # Append
        command_buttons.append(third_row)

        # Send the message
        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_details(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._selected_storage_and_path(menu_state)

        # Lookup file data and metadata
        try:
            _, filename = self.plugin_context.file_manager.split_path(storage_name, file_path)
            file_metadata = self.plugin_context.file_manager.get_metadata(storage_name, file_path) or {}
            analysis = file_metadata.get("analysis") or {}
            statistics = file_metadata.get("statistics") or {}
            history = file_metadata.get("history") or {}
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you were looking for. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.update_menu(command_context, msg, None)
            return

        # Message header
        msg = render_emojis(
            f"{{emo:info}} <b>File details</b>\n\n{{emo:name}} <b>Name:</b> <code>{html.escape(filename)}</code>"
        )

        # Upload timestamp
        try:
            lastmodified = self.plugin_context.file_manager.get_lastmodified(storage_name, file_path)
            if lastmodified is not None:
                dt = datetime.datetime.fromtimestamp(lastmodified).astimezone()
                msg += render_emojis(f"\n{{emo:calendar}} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            self._logger.exception("Caught an exception getting file date")

        # File size
        filesize = self.plugin_context.file_manager.get_size(storage_name, file_path)
        msg += render_emojis(f"\n{{emo:filesize}} <b>Size:</b> {Formatters.format_size(filesize)}")

        # Filament info
        filament_length = 0
        try:
            filament = analysis.get("filament", {})
            if filament:
                msg += render_emojis("\n{emo:filament} <b>Filament:</b> ")
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

        # Dimensions
        dimensions = analysis.get("dimensions", {})
        dimension_parts = []
        if "width" in dimensions:
            dimension_parts.append("{:.2f}mm (X)".format(dimensions["width"]))
        if "depth" in dimensions:
            dimension_parts.append("{:.2f}mm (Y)".format(dimensions["depth"]))
        if "height" in dimensions:
            dimension_parts.append("{:.2f}mm (Z)".format(dimensions["height"]))
        if dimension_parts:
            msg += render_emojis("\n{emo:dimensions} <b>Dimensions:</b> ") + " &#215; ".join(dimension_parts)

        # Print time
        print_time = analysis.get("estimatedPrintTime")
        if print_time:
            msg += render_emojis(
                f"\n{{emo:stopwatch}} <b>Print Time:</b> {Formatters.format_fuzzy_print_time(print_time)}"
            )

            # ETA
            try:
                time_finish = Formatters.format_eta(self.plugin_context.settings, print_time)
                msg += render_emojis(f"\n{{emo:finish}} <b>Completed Time:</b> {html.escape(time_finish)}")
            except Exception:
                self._logger.exception("Caught an exception calculating ETA")

            # Cost calculation (if plugin active)
            if self.plugin_context.plugins.is_enabled("cost") and filament_length:
                try:
                    cp_h = self.plugin_context.cost.cost_per_time
                    cp_m = self.plugin_context.cost.cost_per_length
                    curr = self.plugin_context.cost.currency
                    cost = filament_length / 1000 * cp_m + print_time / 3600 * cp_h
                    msg += render_emojis(f"\n{{emo:cost}} <b>Cost:</b> {html.escape(curr)}{cost:.02f}")
                except Exception:
                    self._logger.exception("Caught an exception calculating cost")

        # Average print times
        try:
            average_print_times = statistics.get("averagePrintTime")
            if average_print_times:
                msg += "\n\n<b>Average Print Time:</b>"
                for profile_id, average_print_time in islice(average_print_times.items(), 5):
                    try:
                        profile = self.plugin_context.printer_profiles.get(profile_id)
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
                    profile = self.plugin_context.printer_profiles.get(profile_id)
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
                        formatted_ts = (
                            datetime.datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        msg += f"\n      Timestamp: {formatted_ts}"

                    print_time = history_entry.get("printTime")
                    if print_time is not None:
                        msg += f"\n      Print Time: {Formatters.format_duration(print_time)}"

                    profile_id = history_entry.get("printerProfile")
                    if profile_id:
                        try:
                            profile = self.plugin_context.printer_profiles.get(profile_id)
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
        imgbb_thumbnail_url = self._upload_thumbnail_to_imgbb(storage_name, file_path)
        if imgbb_thumbnail_url:
            msg = f"<a href='{imgbb_thumbnail_url}'>&#8199;</a>\n{msg}"

        # Create command buttons
        command_buttons = [
            [
                (
                    render_emojis("{emo:back} Back"),
                    f"{command_context.cmd}_info",
                )
            ]
        ]

        # Send the message
        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_settings(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Ask which file browsing setting to change."""
        msg = render_emojis("{emo:question} Which setting do you want to change?")

        command_buttons = [
            [
                (
                    render_emojis("{emo:height} File sorting"),
                    f"{command_context.cmd}_settings_sort",
                ),
                (
                    render_emojis("{emo:model} Show models"),
                    f"{command_context.cmd}_settings_models",
                ),
            ],
            [
                (
                    render_emojis("{emo:back} Back"),
                    f"{command_context.cmd}_list",
                )
            ],
        ]

        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_sort_setting(
        self, command_context: CommandContext, menu_state: FilesMenuState, sort_by_date: bool | None
    ) -> None:
        """Show how files are sorted, and change it when a new value is given.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            menu_state (FilesMenuState): The state of the menu the settings were opened from.
            sort_by_date (bool | None): The value to apply, or None to only show the current one.
        """
        if sort_by_date is not None:
            self.plugin_context.settings.sort_files_by_date = sort_by_date
            self.plugin_context.settings.save()

        current_setting = self.plugin_context.settings.sort_files_by_date
        current_setting_str = "{emo:calendar} By date" if current_setting else "{emo:name} By name"

        msg = render_emojis(
            f"{{emo:question}} <b>Choose file sorting</b>\n\nCurrent setting: <code>{current_setting_str}</code>"
        )

        command_buttons = [
            [
                (
                    render_emojis("{emo:name} By name"),
                    f"{command_context.cmd}_settings_sort_byname",
                ),
                (
                    render_emojis("{emo:calendar} By date"),
                    f"{command_context.cmd}_settings_sort_bydate",
                ),
            ],
            [
                (
                    render_emojis("{emo:back} Back"),
                    f"{command_context.cmd}_settings",
                )
            ],
        ]

        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_models_setting(
        self, command_context: CommandContext, menu_state: FilesMenuState, show_models: bool | None
    ) -> None:
        """Show whether models are listed, and change it when a new value is given.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            menu_state (FilesMenuState): The state of the menu the settings were opened from.
            show_models (bool | None): The value to apply, or None to only show the current one.
        """
        if show_models is not None:
            self.plugin_context.settings.show_models_in_files = show_models
            self.plugin_context.settings.save()

        current_setting = self.plugin_context.settings.show_models_in_files
        current_setting_str = "{emo:online} Show models" if current_setting else "{emo:offline} Hide models"

        msg = render_emojis(
            "{emo:question} <b>Choose whether to show the models</b>\n\n"
            f"Current setting: <code>{current_setting_str}</code>"
        )

        command_buttons = [
            [
                (
                    render_emojis("{emo:online} Show models"),
                    f"{command_context.cmd}_settings_models_show",
                ),
                (
                    render_emojis("{emo:offline} Hide models"),
                    f"{command_context.cmd}_settings_models_hide",
                ),
            ],
            [
                (
                    render_emojis("{emo:back} Back"),
                    f"{command_context.cmd}_settings",
                )
            ],
        ]

        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _copy_move_operation(self, menu_state: FilesMenuState) -> str:
        """Return whether the selected file is being copied or moved.

        Args:
            menu_state (FilesMenuState): The state of the menu the operation was started from.

        Returns:
            str: Either "copy" or "move".

        Raises:
            StaleMenuError: If the menu carries neither.
        """
        if menu_state.operation in ("copy", "move"):
            return menu_state.operation
        raise StaleMenuError

    def _copy_move_destination(self, menu_state: FilesMenuState) -> tuple[str, str]:
        """Return the storage the destination folder is in and its path inside it.

        Args:
            menu_state (FilesMenuState): The state of the menu the destination was picked from.

        Returns:
            tuple[str, str]: The name of the storage, then the path inside it.

        Raises:
            StaleMenuError: If the menu carries no destination.
        """
        if not menu_state.target:
            raise StaleMenuError
        return self._split_storage_and_path(menu_state.target)

    def _file_copy_move_confirmation(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Ask the user to confirm copying or moving the selected file to the destination picked."""
        operation = self._copy_move_operation(menu_state)

        from_storage_name, from_path = self._selected_storage_and_path(menu_state)
        full_from_file_path_to_display = f"/{from_storage_name}/{from_path}"

        to_storage_name, to_path = self._copy_move_destination(menu_state)
        full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")

        command_buttons = [
            [
                (
                    render_emojis("{emo:check} Yes"),
                    f"{command_context.cmd}_copymove_yes",
                ),
                (
                    render_emojis("{emo:cancel} No"),
                    f"{command_context.cmd}_copymove",
                ),
            ]
        ]

        self.update_menu(
            command_context,
            render_emojis(
                f"{{emo:warning}} {operation.capitalize()} <code>{html.escape(full_from_file_path_to_display)}</code> to <code>{html.escape(full_to_file_path_to_display)}</code>?"
            ),
            menu_state,
            markup=Markup.HTML,
            buttons=command_buttons,
        )

    def _file_copy_move(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Copy or move the selected file to the destination picked."""
        operation = self._copy_move_operation(menu_state)

        from_storage_name, from_path = self._selected_storage_and_path(menu_state)
        full_from_file_path_to_display = f"/{from_storage_name}/{from_path}"

        to_storage_name, to_path = self._copy_move_destination(menu_state)
        full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")

        # Copy/move code is adapted from the filemanager plugin: https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
        failure_reason = None
        try:
            if from_storage_name != to_storage_name:
                failure_reason = "Cross-storage operations are not supported"
            elif not self.plugin_context.file_manager.file_exists(from_storage_name, from_path):
                failure_reason = "Source does not exist or isn't a file"
            elif to_path and not self.plugin_context.file_manager.folder_exists(to_storage_name, to_path):
                failure_reason = "Destination doesn't exist or it isn't a folder"
            else:
                _, from_filename = self.plugin_context.file_manager.split_path(from_storage_name, from_path)
                final_to_path = self.plugin_context.file_manager.join_path(to_storage_name, to_path, from_filename)

                if self.plugin_context.file_manager.file_exists(
                    to_storage_name, final_to_path
                ) or self.plugin_context.file_manager.folder_exists(to_storage_name, final_to_path):
                    failure_reason = "Destination already exists"
                else:
                    if operation == "copy":
                        # Copy the file
                        self.plugin_context.file_manager.copy_file(from_storage_name, from_path, final_to_path)
                    elif operation == "move":
                        current_job_file = (self.plugin_context.printer.get_current_data() or {}).get("job", {}).get(
                            "file"
                        ) or {}
                        current_origin = current_job_file.get("origin")
                        current_path = current_job_file.get("path")

                        is_current_file_busy = (
                            current_path is not None
                            and current_origin == from_storage_name
                            and self.plugin_context.file_manager.file_in_path(
                                from_storage_name, from_path, current_path
                            )
                            and (
                                self.plugin_context.printer.is_printing()
                                or self.plugin_context.printer.is_paused()
                                or self.plugin_context.printer.is_pausing()
                                or self.plugin_context.printer.is_resuming()
                                or self.plugin_context.printer.is_cancelling()
                                or self.plugin_context.printer.is_finishing()
                            )
                        )
                        is_busy_in_file_manager = any(
                            from_storage_name == busy_storage
                            and self.plugin_context.file_manager.file_in_path(from_storage_name, from_path, busy_path)
                            for busy_storage, busy_path in self.plugin_context.file_manager.get_busy_files()
                        )

                        if is_current_file_busy or is_busy_in_file_manager:
                            failure_reason = "Source is currently in use"
                        else:
                            # Deselect source file if currently selected
                            if current_origin == from_storage_name and current_path == from_path:
                                if hasattr(self.plugin_context.printer, "set_job"):
                                    # OctoPrint >= 2.0.0
                                    # ty: ignore[invalid-argument-type] - wrong annotation in OctoPrint upstream
                                    self.plugin_context.printer.set_job(None)
                                else:
                                    # OctoPrint < 2.0.0 backwards compatibility
                                    # nosemgrep (this is a fallback for older OctoPrint versions)
                                    self.plugin_context.printer.unselect_file()

                            # Move the file
                            self.plugin_context.file_manager.move_file(from_storage_name, from_path, final_to_path)
                    else:
                        failure_reason = "Unknown operation"

        except Exception:
            self._logger.exception("Caught an exception copying/moving file %s", full_to_file_path_to_display)
            failure_reason = "Internal error, please check logs"

        if failure_reason:
            msg = render_emojis(
                f"{{emo:attention}} Cannot {operation} file <code>{html.escape(full_from_file_path_to_display)}</code> to <code>{html.escape(full_to_file_path_to_display)}</code>"
                f"\nReason: {failure_reason}"
            )

            command_buttons = [
                [
                    (
                        render_emojis("{emo:back} Back"),
                        f"{command_context.cmd}_info",
                    )
                ]
            ]

            self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)
        else:
            if operation == "copy":
                action_done = "copied"
            elif operation == "move":
                action_done = "moved"

            msg = render_emojis(
                f"{{emo:check}} File <code>{html.escape(full_from_file_path_to_display)}</code> {action_done} to <code>{html.escape(full_to_file_path_to_display)}</code>"
            )

            menu_state.folder = "/".join(filter(None, [to_storage_name, to_path]))
            menu_state.page = 0
            command_buttons = [
                [
                    (
                        render_emojis("{emo:back} Back"),
                        f"{command_context.cmd}_list",
                    )
                ]
            ]

            self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_copy_move_destination(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Let the user browse to the folder to copy or move the selected file to."""
        sent_message_id = self.plugin_context.sender.send_message(
            render_emojis("{emo:loading} Loading files..."),
            chat_id=command_context.chat_id,
            message_id=command_context.msg_id_to_update,
            reply_to_message_id=command_context.msg_id_to_reply_to,
        )
        if sent_message_id:
            command_context.msg_id_to_update = sent_message_id

        operation = self._copy_move_operation(menu_state)

        from_storage_name, from_path = self._selected_storage_and_path(menu_state)
        full_from_file_path_to_display = f"/{from_storage_name}/{from_path}"

        storages = self.plugin_context.file_manager.list_files(recursive=False)

        msg = render_emojis(
            f"{{emo:question}} Where do you want to {operation} the file <code>{html.escape(full_from_file_path_to_display)}</code>?"
        )

        command_buttons = []
        menu_state.items = []

        if menu_state.target:  # Start navigation from the target folder
            to_storage_name, to_path = self._split_storage_and_path(menu_state.target)
            full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")

            msg += f"\nCurrent selection: <code>{html.escape(full_to_file_path_to_display)}</code>"

            # Up button
            if to_path or len(storages) > 1:
                command_buttons.append(
                    [
                        (
                            render_emojis("{emo:up} Parent"),
                            f"{command_context.cmd}_copymove_up",
                        )
                    ]
                )

            # Folder buttons
            try:
                to_path_listing = self.plugin_context.file_manager.list_files(
                    locations=to_storage_name,
                    path=to_path,
                    filter=lambda node: node["type"] == "folder",
                    recursive=False,
                )
            except Exception:
                msg = render_emojis(
                    f"{{emo:attention}} The path you were browsing no longer exists. Perhaps you want to have a look at {command_context.cmd} again?"
                )
                self.update_menu(command_context, msg, None)
                return

            to_path_folders = to_path_listing.get(to_storage_name, {})
            for folder_name in sorted(to_path_folders):
                menu_state.items.append("/".join(filter(None, [to_storage_name, to_path, folder_name])))
                command_buttons.append(
                    [
                        (
                            render_emojis(f"{{emo:folder}} {folder_name}"),
                            f"{command_context.cmd}_copymove_{len(menu_state.items) - 1}",
                        )
                    ]
                )

            # Copy/Move here button
            command_buttons.append(
                [
                    (
                        render_emojis(f"{{emo:check}} {operation.capitalize()} here"),
                        f"{command_context.cmd}_copymove_here",
                    )
                ]
            )
        else:  # Select storage
            if len(storages) == 1:
                menu_state.target = next(iter(storages))
                self._file_copy_move_destination(command_context, menu_state)
                return

            for storage_name in storages:
                menu_state.items.append(storage_name)
                command_buttons.append([(storage_name, f"{command_context.cmd}_copymove_{len(menu_state.items) - 1}")])

        # Back button
        command_buttons.append([(render_emojis("{emo:back} Back"), f"{command_context.cmd}_info")])

        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _file_print(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        destination, file = self._selected_storage_and_path(menu_state)

        if not permissions.is_command_allowed(
            self.plugin_context.settings, command_context.chat_id, command_context.from_id, "/print"
        ):
            msg = render_emojis("{emo:notallowed} You are not allowed to print!")
            command_buttons = [
                [
                    (
                        render_emojis("{emo:back} Back"),
                        f"{command_context.cmd}_info",
                    ),
                ]
            ]
            self.update_menu(command_context, msg, menu_state, buttons=command_buttons)
            return

        if not self.plugin_context.printer.is_ready():
            msg = render_emojis(
                f"{{emo:warning}} Can't start a new print, printer is not ready. Printer status: {self.plugin_context.printer.get_state_string()}."
            )
            command_buttons = [
                [
                    (
                        render_emojis("{emo:back} Back"),
                        f"{command_context.cmd}_info",
                    ),
                ]
            ]
            self.update_menu(command_context, msg, menu_state, buttons=command_buttons)
            return

        try:
            if hasattr(self.plugin_context.printer, "set_job"):
                # OctoPrint >= 2.0.0
                job = self.plugin_context.file_manager.create_job(destination, file)
                self.plugin_context.printer.set_job(job, print_after_select=False)
            else:
                # OctoPrint < 2.0.0 backwards compatibility
                is_sd = destination == octoprint.filemanager.FileDestinations.SDCARD
                file_to_select = file if is_sd else self.plugin_context.file_manager.path_on_disk(destination, file)
                # nosemgrep (this is a fallback for older OctoPrint versions)
                self.plugin_context.printer.select_file(file_to_select, sd=is_sd, printAfterSelect=False)
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you wanted to print. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.update_menu(command_context, msg, None)
            return

        current_data = self.plugin_context.printer.get_current_data() or {}
        job_info = (current_data.get("job") or {}).get("file") or {}
        job_file_name = job_info.get("name") or file

        msg = render_emojis(
            f"{{emo:info}} The file <code>{html.escape(job_file_name)}</code> is selected for printing.\n\n"
            "{emo:question} Do you want to start printing it now?"
        )

        command_buttons = [
            [
                (
                    render_emojis("{emo:play} Print"),
                    "/print_yes",
                ),
                (
                    render_emojis("{emo:back} Back"),
                    f"{command_context.cmd}_info",
                ),
            ]
        ]

        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _pick_slice_option(self, menu_state: FilesMenuState, option: str) -> None:
        """Assign a picked option to the first slicing choice still to make.

        Args:
            menu_state (FilesMenuState): The state of the menu the option was picked from.
            option (str): The id of a slicer, of a slicing profile or of a printer profile.
        """
        if menu_state.slicer is None:
            menu_state.slicer = option
        elif menu_state.slicer_profile is None:
            menu_state.slicer_profile = option
        else:
            menu_state.printer_profile = option

    def _clear_slice_choices_from(self, menu_state: FilesMenuState, level: str) -> None:
        """Forget a slicing choice and every choice made after it.

        Args:
            menu_state (FilesMenuState): The state of the menu the choices were made in.
            level (str): Either "slicer", "slicerprofile" or "printerprofile".
        """
        if level == "slicer":
            menu_state.slicer = None
        if level in ("slicer", "slicerprofile"):
            menu_state.slicer_profile = None
        menu_state.printer_profile = None

    def _file_slice(self, command_context: CommandContext, menu_state: FilesMenuState, confirmed: bool) -> None:
        """Ask for the slicing choices still to make, then slice the selected model once confirmed.

        Every choice with a single option is made without asking, so the menus shown depend on how many
        slicers and profiles are configured.

        Args:
            command_context (CommandContext): The details of a single command invocation.
            menu_state (FilesMenuState): The state of the menu the model was selected from.
            confirmed (bool): Whether the user confirmed the choices shown to them.

        Raises:
            StaleMenuError: If the menu carries no selected model.
        """
        # Check if there is at least one configured slicer available
        if not self.plugin_context.slicing_manager.slicing_enabled:
            msg = render_emojis(
                "{emo:attention} No slicer plugin is installed. "
                "Please install one of the plugins listed at the following link: "
                "https://plugins.octoprint.org/by_tag/#tag-slicer"
            )
            self.update_menu(command_context, msg, None)
            return

        # Get selected file data
        storage_name, file_path = self._selected_storage_and_path(menu_state)
        full_file_path_to_display = f"/{storage_name}/{file_path}"

        # Initialize msg
        msg = render_emojis(f"{{emo:slice}} Slicing: <code>{html.escape(full_file_path_to_display)}</code>\n\n")

        # Get slicer id
        configured_slicers = self.plugin_context.slicing_manager.configured_slicers
        if menu_state.slicer is None:
            if len(configured_slicers) == 1:  # If there is only one slicer, automatically select it
                slicer = self.plugin_context.slicing_manager.get_slicer(configured_slicers[0])
                menu_state.slicer = slicer.get_slicer_properties().get("type")
            else:  # If there are multiple slicers, ask to select one
                msg += render_emojis("{emo:question} Which slicer do you want to use?")

                menu_state.items = []
                command_buttons = []
                for configured_slicer in configured_slicers:
                    slicer = self.plugin_context.slicing_manager.get_slicer(configured_slicer)
                    slicer_properties = slicer.get_slicer_properties()

                    menu_state.items.append(slicer_properties.get("type"))

                    slicer_name = slicer_properties.get("name")

                    command_buttons.append([(slicer_name, f"{command_context.cmd}_slice_{len(menu_state.items) - 1}")])
                command_buttons.append([(render_emojis("{emo:back} Back"), f"{command_context.cmd}_info")])

                self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)
                return

        slicer_id = menu_state.slicer

        # Get slicer and slicer properties by slicer id
        if slicer_id is None or slicer_id not in configured_slicers:
            msg = render_emojis("{emo:attention} The slicer you chose is not available")
            self.update_menu(command_context, msg, None)
            return
        slicer = self.plugin_context.slicing_manager.get_slicer(slicer_id)
        slicer_properties = slicer.get_slicer_properties()
        slicer_name = slicer_properties.get("name", "").strip()

        # Add slicer name to msg
        msg += render_emojis(f"{{emo:settings}} Selected slicer: <code>{html.escape(slicer_name)}</code>\n")

        # Get slicer profile id
        slicer_profiles = list(self.plugin_context.slicing_manager.all_profiles(slicer_id).values())
        if menu_state.slicer_profile is None:
            if len(slicer_profiles) == 1:  # If there is only one slicer profile, automatically select it
                menu_state.slicer_profile = slicer_profiles[0].name
            else:  # If there are multiple slicer profiles, ask to select one
                msg += render_emojis("\n{emo:question} Which slicer profile do you want to use?")

                menu_state.items = []
                command_buttons = []
                for slicer_profile in slicer_profiles:
                    menu_state.items.append(slicer_profile.name)

                    slicer_profile_name = slicer_profile.display_name

                    command_buttons.append(
                        [
                            (
                                slicer_profile_name,
                                f"{command_context.cmd}_slice_{len(menu_state.items) - 1}",
                            )
                        ]
                    )
                if len(configured_slicers) > 1:
                    back_cmd = f"{command_context.cmd}_slice_slicer"
                else:
                    back_cmd = f"{command_context.cmd}_info"
                command_buttons.append([(render_emojis("{emo:back} Back"), back_cmd)])

                self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)
                return

        slicer_profile_id = menu_state.slicer_profile

        # Get slicer profile name by slicer profile id and add it to msg
        slicer_profile_name = next((p.display_name.strip() for p in slicer_profiles if p.name == slicer_profile_id), "")
        msg += render_emojis(
            f"{{emo:settings}} Selected slicer profile: <code>{html.escape(slicer_profile_name)}</code>\n"
        )

        # Get printer profile id
        printer_profiles = list(self.plugin_context.printer_profiles.get_all().values())
        if menu_state.printer_profile is None:
            if len(printer_profiles) == 1:  # If there is only one printer profile, automatically select it
                menu_state.printer_profile = printer_profiles[0].get("id")
            else:  # If there are multiple printer profiles, ask to select one
                msg += render_emojis("\n{emo:question} Which printer profile do you want to use?")

                menu_state.items = []
                command_buttons = []
                for printer_profile in printer_profiles:
                    menu_state.items.append(printer_profile.get("id"))

                    printer_profile_name = printer_profile.get("name")

                    command_buttons.append(
                        [
                            (
                                printer_profile_name,
                                f"{command_context.cmd}_slice_{len(menu_state.items) - 1}",
                            )
                        ]
                    )
                if len(slicer_profiles) > 1:
                    back_cmd = f"{command_context.cmd}_slice_slicerprofile"
                elif len(configured_slicers) > 1:
                    back_cmd = f"{command_context.cmd}_slice_slicer"
                else:
                    back_cmd = f"{command_context.cmd}_info"
                command_buttons.append([(render_emojis("{emo:back} Back"), back_cmd)])

                self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)
                return

        printer_profile_id = menu_state.printer_profile

        # Get printer profile name by printer profile id and add it to msg
        printer_profile_name = (
            (self.plugin_context.printer_profiles.get(printer_profile_id) or {}).get("name", "").strip()
        )
        msg += render_emojis(
            f"{{emo:settings}} Selected printer profile: <code>{html.escape(printer_profile_name)}</code>\n"
        )

        # Calculate destination path and add it to msg
        dest_ext = (slicer_properties.get("destination_extensions") or ["gco"])[0]
        file_path_root = os.path.splitext(file_path)[0]
        dest_path = f"{file_path_root}.{dest_ext}"
        dest_path_to_display = f"/{storage_name}/{dest_path}"
        msg += render_emojis(f"\n{{emo:save}} Destination path: <code>{html.escape(dest_path_to_display)}</code>\n")

        # Check confirmation
        if not confirmed:
            msg += render_emojis("\n{emo:question} Do you want to confirm the slicing?")

            if len(printer_profiles) > 1:
                back_cmd = f"{command_context.cmd}_slice_printerprofile"
            elif len(slicer_profiles) > 1:
                back_cmd = f"{command_context.cmd}_slice_slicerprofile"
            elif len(configured_slicers) > 1:
                back_cmd = f"{command_context.cmd}_slice_slicer"
            else:
                back_cmd = f"{command_context.cmd}_info"
            command_buttons = [
                [
                    (render_emojis("{emo:back} Back"), back_cmd),
                    (
                        render_emojis("{emo:check} Confirm"),
                        f"{command_context.cmd}_slice_confirm",
                    ),
                ]
            ]

            self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)
            return

        def slice_callback(*args: object, **kwargs: object) -> None:
            """Report the outcome of the slicing in the chat."""
            _error = kwargs.get("_error")
            _cancelled = kwargs.get("_cancelled")

            if _cancelled:
                msg = render_emojis(
                    f"{{emo:warning}} Slicing of <code>{html.escape(full_file_path_to_display)}</code> has been cancelled"
                )
            elif _error:
                msg = render_emojis(
                    f"{{emo:attention}} Error while slicing <code>{html.escape(full_file_path_to_display)}</code>: {html.escape(str(_error))}"
                )
            else:
                msg = render_emojis(
                    f"{{emo:check}} <code>{html.escape(full_file_path_to_display)}</code> has been successfully sliced to <code>{html.escape(dest_path_to_display)}</code>"
                )

            command_buttons = [
                [
                    (render_emojis("{emo:back} Back"), f"{command_context.cmd}_info"),
                    (
                        render_emojis("{emo:cancel} Close"),
                        "close",
                    ),
                ]
            ]

            self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

        # Perform slicing
        self.plugin_context.file_manager.slice(
            slicer_id,
            octoprint.filemanager.FileDestinations.LOCAL,
            file_path,
            octoprint.filemanager.FileDestinations.LOCAL,
            dest_path,
            profile=slicer_profile_id,
            printer_profile_id=printer_profile_id,
            callback=slice_callback,
        )
        msg = render_emojis(
            f"{{emo:loading}} Slicing <code>{html.escape(full_file_path_to_display)}</code> to <code>{html.escape(dest_path_to_display)}</code>..."
        )

        # Send msg
        self.update_menu(command_context, msg, None, markup=Markup.HTML)

    def _file_download(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._selected_storage_and_path(menu_state)

        try:
            file_path_on_disk = self.plugin_context.file_manager.path_on_disk(storage_name, file_path)
            self.plugin_context.sender.send_file(command_context.chat_id, file_path_on_disk)
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you were looking for. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.update_menu(command_context, msg, None)

    def _file_delete_confirmation(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._selected_storage_and_path(menu_state)
        full_file_path_to_display = f"/{storage_name}/{file_path}"

        command_buttons = [
            [
                (
                    render_emojis("{emo:check} Yes"),
                    f"{command_context.cmd}_delete_yes",
                ),
                (
                    render_emojis("{emo:cancel} No"),
                    f"{command_context.cmd}_info",
                ),
            ]
        ]

        self.update_menu(
            command_context,
            render_emojis(f"{{emo:warning}} Delete <code>{html.escape(full_file_path_to_display)}</code>?"),
            menu_state,
            markup=Markup.HTML,
            buttons=command_buttons,
        )

    def _file_delete(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._selected_storage_and_path(menu_state)
        full_file_path_to_display = f"/{storage_name}/{file_path}"

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
                    if hasattr(self.plugin_context.printer, "set_job"):
                        # OctoPrint >= 2.0.0
                        # ty: ignore[invalid-argument-type] - wrong annotation in OctoPrint upstream
                        self.plugin_context.printer.set_job(None)
                    else:
                        # OctoPrint < 2.0.0 backwards compatibility
                        # nosemgrep (this is a fallback for older OctoPrint versions)
                        self.plugin_context.printer.unselect_file()

                # Delete the file
                if storage_name == octoprint.filemanager.FileDestinations.SDCARD:
                    if hasattr(self.plugin_context.file_manager, "list_storage_entries"):
                        # OctoPrint >= 2.0.0
                        self.plugin_context.file_manager.remove_file(storage_name, file_path)
                    else:
                        # OctoPrint < 2.0.0 backwards compatibility
                        # nosemgrep (this is a fallback for older OctoPrint versions)
                        # ty: ignore[unresolved-attribute] - wrong annotation in OctoPrint upstream
                        self.plugin_context.printer.delete_sd_file(file_path)
                else:
                    self.plugin_context.file_manager.remove_file(storage_name, file_path)
        except Exception:
            self._logger.exception("Caught an exception deleting file %s", file_path)
            failure_reason = "Internal error, please check logs"

        if failure_reason:
            msg = render_emojis(
                f"{{emo:attention}} Cannot delete <code>{html.escape(full_file_path_to_display)}</code>!\n"
                f"Reason: {failure_reason}"
            )
        else:
            msg = render_emojis(f"{{emo:check}} File <code>{html.escape(full_file_path_to_display)}</code> deleted!")

        command_buttons = [
            [
                (
                    render_emojis("{emo:back} Back"),
                    f"{command_context.cmd}_list",
                )
            ]
        ]

        self.update_menu(command_context, msg, menu_state, markup=Markup.HTML, buttons=command_buttons)

    def _upload_thumbnail_to_imgbb(self, storage_name: str, file_path: str) -> str | None:
        """Upload the thumbnail of a file to imgbb and return public URL.

        Args:
            storage_name (str): The storage the file is stored in (e.g., octoprint.filemanager.FileDestinations.LOCAL).
            file_path (str): The path of the file inside its storage.

        Returns:
            str or None: Public URL of uploaded thumbnail or None if failed.
        """
        try:
            api_key = self.plugin_context.settings.imgbb_api_key
            upload_url = "https://api.imgbb.com/1/upload"

            if not api_key:
                return

            thumbnail = self.plugin_context.thumbnails.get_thumbnail(storage_name, file_path)
            if not thumbnail:
                return

            self._logger.info("Uploading to imgbb the thumbnail of %s/%s", storage_name, file_path)

            encoded_img = base64.b64encode(thumbnail)
            payload = {"key": api_key, "image": encoded_img}

            upload_response = requests.post(upload_url, payload)
            if not upload_response.ok:
                return

            return upload_response.json()["data"]["url"]
        except Exception:
            self._logger.exception("Caught an exception uploading thumbnail to imgbb")
