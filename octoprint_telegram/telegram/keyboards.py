from __future__ import annotations

from typing import List, Sequence, Tuple, TypeVar

from ..emoji import Emoji

render_emojis = Emoji.render_emojis

Button = Tuple[str, str]
"""A single button: the label shown to the user, then the callback data sent when it is pressed."""

ButtonRow = List[Button]
"""The buttons shown side by side on one row of an inline keyboard."""

Buttons = List[ButtonRow]
"""The rows of an inline keyboard, from the top one to the bottom one."""

T = TypeVar("T")

Entry = Tuple[T, str, str]
"""An entry of a paginated menu: the item the menu acts on when it is chosen, the label shown, then the action
choosing it runs."""

BACK_LABEL = "{emo:back} Back"
"""The label of the button going back to the menu a command came from."""

CLOSE_BUTTON = ("{emo:cancel} Close", "", "close")
"""The button removing the menu from the chat."""

# Number of rows of entries every page shows
DEFAULT_PAGE_ROWS = 7


class Keyboard:
    """The inline keyboard shown under the answer of a command."""

    def __init__(self, command: str) -> None:
        """Set up the keyboard of a command.

        Args:
            command (str): The command the buttons run when they are pressed.
        """
        self.command = command
        self.rows: Buttons = []

    def add_row(self, *buttons: tuple[str, ...]) -> None:
        """Add one row of buttons, from the leftmost to the rightmost.

        Args:
            *buttons (tuple[str, ...]): For every button, the label shown to the user and the parameter its command
                is run with, plus the command itself when it is not the one the keyboard belongs to.
        """
        row = []
        for button in buttons:
            label, parameter = button[0], button[1]
            command = button[2] if len(button) > 2 else self.command
            row.append((render_emojis(label), f"{command}_{parameter}" if parameter else command))
        self.rows.append(row)

    def add_grid(self, buttons: Sequence[tuple[str, ...]], buttons_per_row: int) -> None:
        """Add buttons over as many rows as they need, filling every row from its leftmost button.

        Args:
            buttons (Sequence[tuple[str, ...]]): The buttons, described as in add_row.
            buttons_per_row (int): The buttons every row holds.
        """
        for row_start in range(0, len(buttons), buttons_per_row):
            self.add_row(*buttons[row_start : row_start + buttons_per_row])

    def add_entries_page(
        self,
        entries: Sequence[Entry[T]],
        entries_per_row: int,
        page: int,
        page_action_prefix: str = "",
        page_rows: int = DEFAULT_PAGE_ROWS,
    ) -> tuple[list[T], int, int]:
        """Add one page of entries, and the buttons to reach the other pages.

        Args:
            entries (Sequence[Entry]): The entries to spread over the pages.
            entries_per_row (int): The entries every row holds.
            page (int): The page to show.
            page_action_prefix (str, optional): What the page-turn actions are prefixed with.
            page_rows (int, optional): The rows of entries every page holds.

        Returns:
            tuple[list[str], int, int]: The item of each entry shown, the page shown, then the number of pages.
        """
        page_size = page_rows * entries_per_row
        total_pages = max(1, (len(entries) + page_size - 1) // page_size)

        page = max(0, min(page, total_pages - 1))
        start_index = page * page_size

        items = []
        entry_buttons = []
        for item, label, action in entries[start_index : start_index + page_size]:
            items.append(item)
            position = len(items) - 1
            entry_buttons.append((label, f"{action}_{position}" if action else str(position)))
        self.add_grid(entry_buttons, buttons_per_row=entries_per_row)

        page_row = []
        if page > 0:
            page_row.append(("{emo:up} Prev page", f"{page_action_prefix}prevpage"))
        if page + 1 < total_pages:
            page_row.append(("{emo:down} Next page", f"{page_action_prefix}nextpage"))
        if page_row:
            self.add_row(*page_row)

        return items, page, total_pages
