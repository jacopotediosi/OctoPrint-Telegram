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
from ..telegram import BACK_LABEL, CLOSE_BUTTON, Keyboard, Markup, MenuState, StaleMenuError
from ..utils import format_duration, format_eta, format_filament, format_fuzzy_print_time, format_size
from .base import BaseCommand, CommandContext

render_emojis = Emoji.render_emojis


class FilesMenuState(MenuState):
    """The entries the menu offers and the operation being carried out on one of them."""

    def __init__(
        self,
        folder: str = "",
        query: str = "",
        page: int = 0,
        items: list[str] | None = None,
        selected: str | None = None,
        operation: str | None = None,
        target: str | None = None,
        slicer: str | None = None,
        slicer_profile: str | None = None,
        printer_profile: str | None = None,
        confirmation: tuple | None = None,
    ) -> None:
        """Set up the entries the menu offers and the operation being carried out on one of them.

        Args:
            folder (str, optional): The folder being browsed, its storage included.
            query (str, optional): The text the names of the files must contain, when files are being searched for.
            page (int, optional): The page of the folder being shown.
            items (list[str], optional): The path of each entry the menu offers, their storage included.
            selected (str, optional): The path the operation acts on, its storage included.
            operation (str, optional): Either "copy" or "move".
            target (str, optional): The folder to copy or move to, its storage included.
            slicer (str, optional): The id of the slicer picked so far.
            slicer_profile (str, optional): The id of the slicing profile picked so far.
            printer_profile (str, optional): The id of the printer profile picked so far.
            confirmation (tuple, optional): The operation the confirmation being shown refers to, with the paths
                it acts on.
        """
        self.folder = folder
        self.query = query
        self.page = page
        self.items = items or []
        self.selected = selected
        self.operation = operation
        self.target = target
        self.slicer = slicer
        self.slicer_profile = slicer_profile
        self.printer_profile = printer_profile
        self.confirmation = confirmation


class CmdFiles(BaseCommand):
    # Number of items (folders + files) to display per page
    PAGE_SIZE = 14

    # Characters of the text to search for that are taken into account, the ones in excess being dropped
    MAX_QUERY_LENGTH = 20

    @override
    def execute(self, command_context: CommandContext) -> None:
        """Browse and manage files.

        The callback query carries the action and, when the action is about one of the entries on
        screen, the position of that entry. The paths themselves travel in the menu state.

        Possible callback queries, where {position} stands for the position of an entry:

        Browsing:
        - /files -> show the storage menu, or the root of the only storage there is
        - /files_list_{position} -> open the folder at that position
        - /files_list -> show the folder being browsed, or the search being shown, at the page it was left on
        - /files_up -> leave the search being shown, or open the parent of the folder being browsed
        - /files_prevpage -> show the previous page of the folder being browsed
        - /files_nextpage -> show the next page of the folder being browsed

        Searching:
        - /files_search -> ask for the text the names of the files must contain
        - /files_search_{text} -> show the files whose name contains that text, in the folder being browsed
          and in all of its subfolders

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

        if (action, argument) not in (("delete", "yes"), ("copymove", "yes")):
            menu_state.confirmation = None

        if action == "list":
            if argument:
                menu_state.folder = self.require_menu_chosen_item(menu_state.items, argument)
                menu_state.page = 0
            self._file_list(command_context, menu_state)

        elif action == "up":
            if menu_state.query:
                menu_state.query = ""
            else:
                menu_state.folder = "/".join(menu_state.folder.split("/")[:-1])
            menu_state.page = 0
            self._file_list(command_context, menu_state)

        elif action == "search":
            query = argument.strip()[: self.MAX_QUERY_LENGTH]
            if query:
                menu_state.query = query
                menu_state.page = 0
                self._file_list(command_context, menu_state)
            else:
                self._file_search_prompt(command_context, menu_state)

        elif action in ("prevpage", "nextpage"):
            menu_state.page += -1 if action == "prevpage" else 1
            self._file_list(command_context, menu_state)

        elif action == "info":
            if argument:
                menu_state.selected = self.require_menu_chosen_item(menu_state.items, argument)
            self._file_info(command_context, menu_state)

        elif action == "details":
            self._file_details(command_context, menu_state)

        elif action == "settings":
            setting, _, value = argument.partition("_")
            if setting == "sort":
                self._file_sort_setting(command_context, menu_state, {"byname": False, "bydate": True}.get(value))
            elif setting == "models":
                self._file_models_setting(command_context, menu_state, {"hide": False, "show": True}.get(value))
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
                    menu_state.target = self.require_menu_chosen_item(menu_state.items, argument)
                self._file_copy_move_destination(command_context, menu_state)

        elif action == "selectforprint":
            self._file_print(command_context, menu_state)

        elif action == "slice":
            if not argument:
                self._clear_slice_choices_from(menu_state, "slicer")
            elif argument.isdigit():
                self._pick_slice_option(menu_state, self.require_menu_chosen_item(menu_state.items, argument))
            elif argument in ("slicer", "slicerprofile", "printerprofile"):
                self._clear_slice_choices_from(menu_state, argument)
            self._file_slice(command_context, menu_state, confirmed=argument == "confirm")

    def _split_storage_and_path(self, path_with_storage: str) -> tuple[str, str]:
        """Return the storage a path is in and the path inside it.

        Args:
            path_with_storage (str): The path, its storage included.

        Returns:
            tuple[str, str]: The name of the storage, then the path inside it.
        """
        storage_name, _, path_without_storage = path_with_storage.partition("/")
        return storage_name, path_without_storage

    def _get_selected_storage_and_path(self, menu_state: FilesMenuState) -> tuple[str, str]:
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

    def _is_file_busy(self, storage_name: str, file_path: str) -> bool:
        """Whether a file is being printed or sliced.

        Args:
            storage_name (str): The storage the file is stored in (e.g., octoprint.filemanager.FileDestinations.LOCAL).
            file_path (str): The path of the file inside its storage.

        Returns:
            bool: True if the file is in use.
        """
        current_data = self.plugin_context.printer.get_current_data() or {}
        job_file = (current_data.get("job") or {}).get("file") or {}
        state_flags = (current_data.get("state") or {}).get("flags") or {}

        # Being printed
        if (
            job_file.get("origin") == storage_name
            and job_file.get("path")
            and self.plugin_context.file_manager.file_in_path(storage_name, file_path, job_file["path"])
            and any(
                state_flags.get(flag)
                for flag in ("printing", "paused", "pausing", "resuming", "cancelling", "finishing")
            )
        ):
            return True

        # Being sliced
        return any(
            storage_name == busy_storage
            and self.plugin_context.file_manager.file_in_path(storage_name, file_path, busy_path)
            for busy_storage, busy_path in self.plugin_context.file_manager.get_busy_files()
        )

    def _file_list(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        self.send_answer(command_context, render_emojis("{emo:loading} Loading files..."), menu_state)

        storages = self.plugin_context.file_manager.registered_storages

        if not menu_state.folder:  # Show storage selection
            if len(storages) == 1:
                menu_state.folder = next(iter(storages))
                self._file_list(command_context, menu_state)
            elif len(storages) > 1:
                msg = render_emojis("{emo:save} <b>Select Storage</b>")

                menu_state.items = list(storages)

                keyboard = Keyboard(command_context.cmd)
                keyboard.add_grid(
                    [
                        (f"{{emo:folder}} {storage_name}", f"list_{storage_position}")
                        for storage_position, storage_name in enumerate(menu_state.items)
                    ],
                    buttons_per_row=1,
                )
                keyboard.add_row(CLOSE_BUTTON)

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

        else:  # List files in path
            path_with_storage = menu_state.folder  # e.g.: local or local/foo
            path_parts = path_with_storage.split("/")
            storage_name = path_parts[0]  # e.g.: local
            path_without_storage = "/".join(path_parts[1:])  # e.g.: '' or foo
            path_is_storage_root = len(path_parts) < 2

            try:
                file_listing = self.plugin_context.file_manager.list_files(
                    storage_name, path_without_storage, recursive=bool(menu_state.query)
                )
            except Exception:
                msg = render_emojis(
                    f"{{emo:attention}} The path you were browsing no longer exists. Perhaps you want to have a look at {command_context.cmd} again?"
                )
                self.send_answer(command_context, msg, None)
                return

            path_content = file_listing.get(storage_name, {})

            # --- Collect the entries to show ---
            if menu_state.query:
                entries = self._get_matching_file_entries(path_with_storage, path_content, menu_state.query)
                entries_per_row = 1
            else:
                entries = self._get_folder_and_file_entries(path_with_storage, path_content)
                entries_per_row = 2

            # --- Calculate pagination ---
            total_pages = max(1, (len(entries) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

            menu_state.page = max(0, min(menu_state.page, total_pages - 1))
            start_index = menu_state.page * self.PAGE_SIZE
            paginated_entries = entries[start_index : start_index + self.PAGE_SIZE]

            # --- Create command buttons ---
            keyboard = Keyboard(command_context.cmd)
            menu_state.items = []

            # Folder and file buttons
            entry_buttons = []
            for entry_path, entry_label, entry_action in paginated_entries:
                menu_state.items.append(entry_path)
                entry_buttons.append((entry_label, f"{entry_action}_{len(menu_state.items) - 1}"))
            keyboard.add_grid(entry_buttons, buttons_per_row=entries_per_row)

            # Prev/next page row
            page_row = []
            if menu_state.page > 0:
                page_row.append(("{emo:up} Prev page", "prevpage"))
            if menu_state.page + 1 < total_pages:
                page_row.append(("{emo:down} Next page", "nextpage"))
            if page_row:
                keyboard.add_row(*page_row)

            # Actions row: search, settings, back, close
            actions_row = []

            # Search
            if not menu_state.query:
                actions_row.append(("{emo:search} Search", "search"))

            # Settings
            actions_row.append(("{emo:settings} Settings", "settings"))

            # Back button (out of the search being shown, to the parent folder, or to the storage selection)
            if menu_state.query or not path_is_storage_root:
                actions_row.append((BACK_LABEL, "up"))
            elif len(storages) > 1:
                actions_row.append((BACK_LABEL, ""))

            # Close
            actions_row.append(CLOSE_BUTTON)

            keyboard.add_row(*actions_row)

            # --- Create message ---
            page_str = f"    [{menu_state.page + 1} / {total_pages}]" if total_pages > 1 else ""
            if menu_state.query:
                msg = render_emojis(
                    f"{{emo:search}} Files matching <code>{html.escape(menu_state.query)}</code> "
                    f"in <code>/{html.escape(path_with_storage)}</code>{page_str}"
                )
                if not entries:
                    msg += "\n\nNo file found."
            else:
                msg = render_emojis(f"{{emo:save}} Files in <code>/{html.escape(path_with_storage)}</code>{page_str}")

            # --- Send message ---
            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _get_file_types_to_show(self) -> tuple[str, ...]:
        """The types of the files the menu lists, as configured in the browsing settings."""
        return ("machinecode", "model") if self.plugin_context.settings.show_models_in_files else ("machinecode",)

    def _get_file_date(self, file_data: dict) -> float:
        """Return the moment a file was uploaded, as a timestamp.

        Args:
            file_data (dict): The data OctoPrint holds about the file.

        Returns:
            float: The timestamp, or 0 for the files whose date OctoPrint does not report.
        """
        # OctoPrint 2 reports a datetime, the previous versions a timestamp
        date = file_data.get("date")
        if isinstance(date, datetime.datetime):
            return date.timestamp()
        return date or 0

    def _get_file_label(self, display_name: str, file_data: dict) -> str:
        """Return the label of the button of a file, telling how its last print went.

        Args:
            display_name (str): The name of the file, as it is shown to the user.
            file_data (dict): The data OctoPrint holds about the file.

        Returns:
            str: The label of the button.
        """
        if file_data.get("type") == "model":
            return render_emojis(f"{{emo:model}} {display_name}")

        try:
            if "history" not in file_data:
                return render_emojis(f"{{emo:new}} {display_name}")

            history_list = file_data["history"]
            if not history_list:
                return render_emojis(f"{{emo:file}} {display_name}")

            last_print = max(history_list, key=lambda history_entry: history_entry.get("timestamp", 0))
            if last_print.get("success"):
                return render_emojis(f"{{emo:hooray}} {display_name}")
            return render_emojis(f"{{emo:warning}} {display_name}")
        except Exception:
            self._logger.exception("Error processing history for file '%s'", display_name)
            return render_emojis(f"{{emo:file}} {display_name}")

    def _get_folder_and_file_entries(self, folder: str, folder_content: dict) -> list[tuple[str, str, str]]:
        """Return the folders and the files a folder holds, in the order the menu offers them.

        Args:
            folder (str): The folder being browsed, its storage included.
            folder_content (dict): The entries the folder holds, as OctoPrint lists them.

        Returns:
            list[tuple[str, str, str]]: For each entry, its path with the storage included, the label of its button
                and the action the button runs.
        """
        entries = []

        folder_names = [name for name, data in folder_content.items() if data.get("type") == "folder"]
        for folder_name in sorted(folder_names):
            entries.append(
                (
                    f"{folder}/{folder_name}",
                    render_emojis(f"{{emo:folder}} {folder_name}"),
                    "list",
                )
            )

        file_types_to_show = self._get_file_types_to_show()
        files = [(name, data) for name, data in folder_content.items() if data.get("type") in file_types_to_show]
        if self.plugin_context.settings.sort_files_by_date:
            files.sort(key=lambda file: self._get_file_date(file[1]), reverse=True)
        else:
            files.sort(key=lambda file: file[0])
        for file_name, file_data in files:
            entries.append(
                (
                    f"{folder}/{file_name}",
                    self._get_file_label(file_name.rsplit(".", 1)[0], file_data),
                    "info",
                )
            )

        return entries

    def _get_matching_file_entries(self, folder: str, folder_content: dict, query: str) -> list[tuple[str, str, str]]:
        """Return the files a folder and its subfolders hold whose name contains a text.

        Args:
            folder (str): The folder being searched, its storage included.
            folder_content (dict): The entries the folder holds, as OctoPrint lists them recursively.
            query (str): The text the names of the files must contain, matched ignoring case.

        Returns:
            list[tuple[str, str, str]]: For each file found, its path with the storage included, the label of its
                button and the action the button runs.
        """
        file_types_to_show = self._get_file_types_to_show()
        query = query.lower()

        matches = []

        def collect_matches(content: dict, path_in_folder: str) -> None:
            """Collect the files of a folder and of its subfolders whose name contains the text."""
            for name, data in content.items():
                if data.get("type") == "folder":
                    collect_matches(data.get("children") or {}, f"{path_in_folder}{name}/")
                elif data.get("type") in file_types_to_show and query in name.lower():
                    matches.append((f"{path_in_folder}{name}", data))

        collect_matches(folder_content, "")

        if self.plugin_context.settings.sort_files_by_date:
            matches.sort(key=lambda match: self._get_file_date(match[1]), reverse=True)
        else:
            matches.sort(key=lambda match: match[0])

        return [
            (
                f"{folder}/{file_path_in_folder}",
                self._get_file_label(file_path_in_folder.rsplit(".", 1)[0], file_data),
                "info",
            )
            for file_path_in_folder, file_data in matches
        ]

    def _file_search_prompt(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Ask the user to answer with the text the names of the files must contain."""
        msg = render_emojis(
            "{emo:search} Reply to this message with the text to look for in the names of the files in "
            f"<code>/{html.escape(menu_state.folder)}</code> and in its subfolders "
            f"(at most {self.MAX_QUERY_LENGTH} characters)"
        )

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row((BACK_LABEL, "list"))

        self.send_answer(
            command_context,
            msg,
            menu_state,
            markup=Markup.HTML,
            keyboard=keyboard,
            force_reply=True,
            reply_parameter_prefix="search_",
            delete_answer_message=True,
        )

    def _get_file_summary(self, filename: str, file_data: dict) -> str:
        """Return the summary of a file.

        Args:
            filename (str): The name of the file, without the folders leading to it.
            file_data (dict): The data OctoPrint holds about the file.

        Returns:
            str: The lines making up the summary.
        """
        analysis = file_data.get("analysis") or {}
        history = file_data.get("history") or []

        # Name
        msg = render_emojis(f"\n{{emo:name}} <b>Name:</b> <code>{html.escape(filename)}</code>")

        # Upload timestamp
        date = self._get_file_date(file_data)
        if date:
            dt = datetime.datetime.fromtimestamp(date).astimezone()
            msg += render_emojis(f"\n{{emo:calendar}} <b>Uploaded:</b> {dt.strftime('%Y-%m-%d %H:%M:%S')}")

        # Number of prints
        if "model" not in octoprint.filemanager.get_file_type(filename):
            if not history:
                msg += render_emojis("\n{emo:new} <b>Number of Prints:</b> 0")
            else:
                try:
                    last_print = max(history, key=lambda entry: entry["timestamp"])
                    success = last_print.get("success", False)
                    icon_name = "hooray" if success else "warning"
                except Exception:
                    self._logger.exception("Caught an exception getting number of prints")
                    icon_name = "file"
                msg += render_emojis(f"\n{{emo:{icon_name}}} <b>Number of Prints:</b> {len(history)}")

        # File size
        filesize = file_data.get("size")
        msg += render_emojis(f"\n{{emo:filesize}} <b>Size:</b> {format_size(filesize)}")

        # Dimensions
        dimensions = analysis.get("dimensions") or {}
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
                if len(filament) == 1 and filament.get("tool0", {}).get("length") is not None:
                    msg += format_filament(filament["tool0"])
                    filament_length += float(filament["tool0"]["length"])
                else:
                    for tool in sorted(filament):
                        length = filament[tool].get("length")
                        if length is not None:
                            msg += f"\n      {html.escape(tool)}: {format_filament(filament[tool])}"
                            filament_length += float(length)
        except Exception:
            self._logger.exception("Caught an exception getting filament info")

        # Print time
        print_time = analysis.get("estimatedPrintTime")
        if print_time:
            msg += render_emojis(f"\n{{emo:stopwatch}} <b>Print Time:</b> {format_fuzzy_print_time(print_time)}")

            # ETA
            try:
                time_finish = format_eta(self.plugin_context.settings, print_time)
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

        return msg

    def _file_info(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._get_selected_storage_and_path(menu_state)

        # Lookup file data
        try:
            folder, filename = self.plugin_context.file_manager.split_path(storage_name, file_path)
            file_listing = self.plugin_context.file_manager.list_files(storage_name, folder, recursive=False)
            file_data = file_listing[storage_name][filename]
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you were looking for. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.send_answer(command_context, msg, None)
            return

        msg = render_emojis("{emo:info} <b>File information</b>\n")
        msg += self._get_file_summary(filename, file_data)

        # Upload the thumbnail image to imgbb to get a public URL
        imgbb_thumbnail_url = self._upload_thumbnail_to_imgbb(storage_name, file_path)
        if imgbb_thumbnail_url:
            msg = f"<a href='{imgbb_thumbnail_url}'>&#8199;</a>\n{msg}"

        # Create command buttons
        keyboard = Keyboard(command_context.cmd)

        # First row
        if "model" in octoprint.filemanager.get_file_type(filename):
            # Slice
            keyboard.add_row(("{emo:slice} Slice", "slice"))
        else:
            # Print + Details
            keyboard.add_row(("{emo:play} Print", "selectforprint"), ("{emo:search} Details", "details"))

        # Second row: File ops
        keyboard.add_row(("{emo:cut} Move", "move"), ("{emo:copy} Copy", "copy"), ("{emo:delete} Delete", "delete"))

        # Third row
        third_row = []
        # Download button
        if storage_name == octoprint.filemanager.FileDestinations.LOCAL:
            third_row.append(("{emo:download} Download", "download"))
        # Back button
        third_row.append((BACK_LABEL, "list"))
        # Append
        keyboard.add_row(*third_row)

        # Send the message
        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _file_details(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._get_selected_storage_and_path(menu_state)

        # Lookup file data
        try:
            folder, filename = self.plugin_context.file_manager.split_path(storage_name, file_path)
            file_listing = self.plugin_context.file_manager.list_files(storage_name, folder, recursive=False)
            file_data = file_listing[storage_name][filename]
            statistics = file_data.get("statistics") or {}
            history = sorted(
                file_data.get("history") or [], key=lambda entry: entry.get("timestamp") or 0, reverse=True
            )
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you were looking for. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.send_answer(command_context, msg, None)
            return

        msg = render_emojis("{emo:info} <b>File details</b>\n")
        msg += self._get_file_summary(filename, file_data)

        # Average print times
        try:
            average_print_times = statistics.get("averagePrintTime")
            if average_print_times:
                msg += "\n\n<b>Average Print Time:</b>"
                for profile_id, average_print_time in islice(average_print_times.items(), 5):
                    try:
                        profile = self.plugin_context.printer_profiles.get(profile_id)
                        msg += f"\n      {html.escape(profile['name'])}: {format_duration(average_print_time)}"
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
                    msg += f"\n      {html.escape(profile['name'])}: {format_duration(last_print_time)}"
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
                        # OctoPrint 2 reports a datetime, the previous versions a timestamp
                        if not isinstance(timestamp, datetime.datetime):
                            timestamp = datetime.datetime.fromtimestamp(timestamp).astimezone()
                        formatted_ts = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                        msg += f"\n      Timestamp: {formatted_ts}"

                    print_time = history_entry.get("printTime")
                    if print_time is not None:
                        msg += f"\n      Print Time: {format_duration(print_time)}"

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
        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row((BACK_LABEL, "info"))

        # Send the message
        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _file_settings(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Ask which file browsing setting to change."""
        msg = render_emojis("{emo:question} Which setting do you want to change?")

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(("{emo:height} File sorting", "settings_sort"), ("{emo:model} Show models", "settings_models"))
        keyboard.add_row((BACK_LABEL, "list"))

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

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

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(
            ("{emo:name} By name", "settings_sort_byname"), ("{emo:calendar} By date", "settings_sort_bydate")
        )
        keyboard.add_row((BACK_LABEL, "settings"))

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

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

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(
            ("{emo:online} Show models", "settings_models_show"), ("{emo:offline} Hide models", "settings_models_hide")
        )
        keyboard.add_row((BACK_LABEL, "settings"))

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

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

        from_storage_name, from_path = self._get_selected_storage_and_path(menu_state)
        full_from_file_path_to_display = f"/{from_storage_name}/{from_path}"

        to_storage_name, to_path = self._copy_move_destination(menu_state)
        full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")

        menu_state.confirmation = (menu_state.operation, menu_state.selected, menu_state.target)

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(("{emo:check} Yes", "copymove_yes"), ("{emo:cancel} No", "copymove"))

        self.send_answer(
            command_context,
            render_emojis(
                f"{{emo:warning}} {operation.capitalize()} <code>{html.escape(full_from_file_path_to_display)}</code> to <code>{html.escape(full_to_file_path_to_display)}</code>?"
            ),
            menu_state,
            markup=Markup.HTML,
            keyboard=keyboard,
        )

    def _file_copy_move(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Copy or move the selected file to the destination picked.

        Raises:
            StaleMenuError: If the confirmation being shown is not for this operation and these paths.
        """
        if menu_state.confirmation != (menu_state.operation, menu_state.selected, menu_state.target):
            raise StaleMenuError
        menu_state.confirmation = None

        operation = self._copy_move_operation(menu_state)

        from_storage_name, from_path = self._get_selected_storage_and_path(menu_state)
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
                        if self._is_file_busy(from_storage_name, from_path):
                            failure_reason = "Source is currently in use"
                        else:
                            # Deselect source file if currently selected
                            current_data = self.plugin_context.printer.get_current_data() or {}
                            job_file = (current_data.get("job") or {}).get("file") or {}
                            if job_file.get("origin") == from_storage_name and job_file.get("path") == from_path:
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

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, "info"))

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
        else:
            if operation == "copy":
                action_done = "copied"
            elif operation == "move":
                action_done = "moved"

            msg = render_emojis(
                f"{{emo:check}} File <code>{html.escape(full_from_file_path_to_display)}</code> {action_done} to <code>{html.escape(full_to_file_path_to_display)}</code>"
            )

            menu_state.folder = "/".join(filter(None, [to_storage_name, to_path]))
            menu_state.query = ""
            menu_state.page = 0

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, "list"))

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _file_copy_move_destination(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Let the user browse to the folder to copy or move the selected file to."""
        self.send_answer(command_context, render_emojis("{emo:loading} Loading files..."), menu_state)

        operation = self._copy_move_operation(menu_state)

        from_storage_name, from_path = self._get_selected_storage_and_path(menu_state)
        full_from_file_path_to_display = f"/{from_storage_name}/{from_path}"

        storages = self.plugin_context.file_manager.list_files(recursive=False)

        msg = render_emojis(
            f"{{emo:question}} Where do you want to {operation} the file <code>{html.escape(full_from_file_path_to_display)}</code>?"
        )

        keyboard = Keyboard(command_context.cmd)
        menu_state.items = []

        if menu_state.target:  # Start navigation from the target folder
            to_storage_name, to_path = self._split_storage_and_path(menu_state.target)
            full_to_file_path_to_display = f"/{to_storage_name}/{to_path}".rstrip("/")

            msg += f"\nCurrent selection: <code>{html.escape(full_to_file_path_to_display)}</code>"

            # Up button
            if to_path or len(storages) > 1:
                keyboard.add_row(("{emo:up} Parent", "copymove_up"))

            # Folder buttons
            try:
                to_path_listing = self.plugin_context.file_manager.list_files(
                    to_storage_name,
                    to_path,
                    filter=lambda node: node["type"] == "folder",
                    recursive=False,
                )
            except Exception:
                msg = render_emojis(
                    f"{{emo:attention}} The path you were browsing no longer exists. Perhaps you want to have a look at {command_context.cmd} again?"
                )
                self.send_answer(command_context, msg, None)
                return

            to_path_folders = to_path_listing.get(to_storage_name, {})
            for folder_name in sorted(to_path_folders):
                menu_state.items.append("/".join(filter(None, [to_storage_name, to_path, folder_name])))
                keyboard.add_row((f"{{emo:folder}} {folder_name}", f"copymove_{len(menu_state.items) - 1}"))

            # Copy/Move here button
            keyboard.add_row((f"{{emo:check}} {operation.capitalize()} here", "copymove_here"))
        else:  # Select storage
            if len(storages) == 1:
                menu_state.target = next(iter(storages))
                self._file_copy_move_destination(command_context, menu_state)
                return

            for storage_name in storages:
                menu_state.items.append(storage_name)
                keyboard.add_row((storage_name, f"copymove_{len(menu_state.items) - 1}"))

        # Back button
        keyboard.add_row((BACK_LABEL, "info"))

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

    def _file_print(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        destination, file = self._get_selected_storage_and_path(menu_state)

        if not permissions.is_command_allowed(
            self.plugin_context.settings, command_context.chat_id, command_context.from_id, "/print"
        ):
            msg = render_emojis("{emo:notallowed} You are not allowed to print!")

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, "info"))

            self.send_answer(command_context, msg, menu_state, keyboard=keyboard)
            return

        if not self.plugin_context.printer.is_ready():
            msg = render_emojis(
                f"{{emo:warning}} Can't start a new print, printer is not ready. Printer status: {self.plugin_context.printer.get_state_string()}."
            )
            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, "info"))

            self.send_answer(command_context, msg, menu_state, keyboard=keyboard)
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
            self.send_answer(command_context, msg, None)
            return

        current_data = self.plugin_context.printer.get_current_data() or {}
        job_info = (current_data.get("job") or {}).get("file") or {}
        job_file_name = job_info.get("name") or file

        msg = render_emojis(
            f"{{emo:info}} The file <code>{html.escape(job_file_name)}</code> is selected for printing.\n\n"
            "{emo:question} Do you want to start printing it now?"
        )

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(("{emo:play} Print", "yes", "/print"), (BACK_LABEL, "info"))

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

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
            self.send_answer(command_context, msg, None)
            return

        # Get selected file data
        storage_name, file_path = self._get_selected_storage_and_path(menu_state)
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
                keyboard = Keyboard(command_context.cmd)
                for configured_slicer in configured_slicers:
                    slicer = self.plugin_context.slicing_manager.get_slicer(configured_slicer)
                    slicer_properties = slicer.get_slicer_properties()

                    menu_state.items.append(slicer_properties.get("type"))

                    slicer_name = slicer_properties.get("name")

                    keyboard.add_row((slicer_name, f"slice_{len(menu_state.items) - 1}"))
                keyboard.add_row((BACK_LABEL, "info"))

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
                return

        slicer_id = menu_state.slicer

        # Get slicer and slicer properties by slicer id
        if slicer_id is None or slicer_id not in configured_slicers:
            msg = render_emojis("{emo:attention} The slicer you chose is not available")
            self.send_answer(command_context, msg, None)
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
                keyboard = Keyboard(command_context.cmd)
                for slicer_profile in slicer_profiles:
                    menu_state.items.append(slicer_profile.name)

                    slicer_profile_name = slicer_profile.display_name or slicer_profile.name

                    keyboard.add_row((slicer_profile_name, f"slice_{len(menu_state.items) - 1}"))
                if len(configured_slicers) > 1:
                    back_action = "slice_slicer"
                else:
                    back_action = "info"
                keyboard.add_row((BACK_LABEL, back_action))

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
                return

        slicer_profile_id = menu_state.slicer_profile

        # Get slicer profile name by slicer profile id and add it to msg
        slicer_profile_name = next(
            ((p.display_name or p.name).strip() for p in slicer_profiles if p.name == slicer_profile_id), None
        )
        if slicer_profile_name is None:
            msg = render_emojis("{emo:attention} The slicer profile you chose is not available")
            self.send_answer(command_context, msg, None)
            return
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
                keyboard = Keyboard(command_context.cmd)
                for printer_profile in printer_profiles:
                    menu_state.items.append(printer_profile.get("id"))

                    printer_profile_name = printer_profile.get("name")

                    keyboard.add_row((printer_profile_name, f"slice_{len(menu_state.items) - 1}"))
                if len(slicer_profiles) > 1:
                    back_action = "slice_slicerprofile"
                elif len(configured_slicers) > 1:
                    back_action = "slice_slicer"
                else:
                    back_action = "info"
                keyboard.add_row((BACK_LABEL, back_action))

                self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
                return

        printer_profile_id = menu_state.printer_profile

        # Get printer profile name by printer profile id and add it to msg
        selected_printer_profile = self.plugin_context.printer_profiles.get(printer_profile_id)
        if selected_printer_profile is None:
            msg = render_emojis("{emo:attention} The printer profile you chose is not available")
            self.send_answer(command_context, msg, None)
            return
        printer_profile_name = selected_printer_profile.get("name", "").strip()
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
                back_action = "slice_printerprofile"
            elif len(slicer_profiles) > 1:
                back_action = "slice_slicerprofile"
            elif len(configured_slicers) > 1:
                back_action = "slice_slicer"
            else:
                back_action = "info"

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, back_action), ("{emo:check} Confirm", "slice_confirm"))

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)
            return

        def slice_callback(*_args: object, **kwargs: object) -> None:
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

            keyboard = Keyboard(command_context.cmd)
            keyboard.add_row((BACK_LABEL, "info"), CLOSE_BUTTON)

            self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

        # Send msg
        msg = render_emojis(
            f"{{emo:loading}} Slicing <code>{html.escape(full_file_path_to_display)}</code> to <code>{html.escape(dest_path_to_display)}</code>..."
        )
        self.send_answer(command_context, msg, None, markup=Markup.HTML)

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

    def _file_download(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._get_selected_storage_and_path(menu_state)

        try:
            file_path_on_disk = self.plugin_context.file_manager.path_on_disk(storage_name, file_path)
            self.plugin_context.sender.send_file(command_context.chat_id, file_path_on_disk)
        except Exception:
            msg = render_emojis(
                f"{{emo:attention}} I couldn't find the file you were looking for. Perhaps you want to have a look at {command_context.cmd} again?"
            )
            self.send_answer(command_context, msg, None)

    def _file_delete_confirmation(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        storage_name, file_path = self._get_selected_storage_and_path(menu_state)
        full_file_path_to_display = f"/{storage_name}/{file_path}"

        menu_state.confirmation = ("delete", menu_state.selected)

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row(("{emo:check} Yes", "delete_yes"), ("{emo:cancel} No", "info"))

        self.send_answer(
            command_context,
            render_emojis(f"{{emo:warning}} Delete <code>{html.escape(full_file_path_to_display)}</code>?"),
            menu_state,
            markup=Markup.HTML,
            keyboard=keyboard,
        )

    def _file_delete(self, command_context: CommandContext, menu_state: FilesMenuState) -> None:
        """Delete the selected file.

        Raises:
            StaleMenuError: If the confirmation being shown is not for deleting this file.
        """
        if menu_state.confirmation != ("delete", menu_state.selected):
            raise StaleMenuError
        menu_state.confirmation = None

        storage_name, file_path = self._get_selected_storage_and_path(menu_state)
        full_file_path_to_display = f"/{storage_name}/{file_path}"

        # Deletion code is adapted from the filemanager plugin: https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
        failure_reason = None
        try:
            if not self.plugin_context.file_manager.file_exists(storage_name, file_path):
                failure_reason = "File doesn't exist or isn't a file"
            elif self._is_file_busy(storage_name, file_path):
                failure_reason = "File is currently in use"
            else:
                # Deselect file if currently selected
                current_data = self.plugin_context.printer.get_current_data() or {}
                job_file = (current_data.get("job") or {}).get("file") or {}
                if job_file.get("origin") == storage_name and job_file.get("path") == file_path:
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

        keyboard = Keyboard(command_context.cmd)
        keyboard.add_row((BACK_LABEL, "list"))

        self.send_answer(command_context, msg, menu_state, markup=Markup.HTML, keyboard=keyboard)

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
                return None

            thumbnail = self.plugin_context.thumbnails.get_thumbnail(storage_name, file_path)
            if not thumbnail:
                return None

            self._logger.info("Uploading to imgbb the thumbnail of %s/%s", storage_name, file_path)

            encoded_img = base64.b64encode(thumbnail)
            payload = {"key": api_key, "image": encoded_img}

            upload_response = requests.post(upload_url, data=payload, timeout=30)
            if not upload_response.ok:
                return None

            return upload_response.json()["data"]["url"]
        except Exception:
            self._logger.exception("Caught an exception uploading thumbnail to imgbb")
