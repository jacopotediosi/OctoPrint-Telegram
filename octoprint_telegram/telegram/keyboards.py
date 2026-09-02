from __future__ import annotations

from typing import List, Sequence, Tuple

from ..emoji import Emoji

render_emojis = Emoji.render_emojis

Button = Tuple[str, str]
"""A single button: the label shown to the user, then the callback data sent when it is pressed."""

ButtonRow = List[Button]
"""The buttons shown side by side on one row of an inline keyboard."""

Buttons = List[ButtonRow]
"""The rows of an inline keyboard, from the top one to the bottom one."""

BACK_LABEL = "{emo:back} Back"
"""The label of the button going back to the menu a command came from."""

CLOSE_BUTTON = ("{emo:cancel} Close", "", "close")
"""The button removing the menu from the chat."""


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
