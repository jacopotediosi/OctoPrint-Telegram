from typing import List, Tuple

Button = Tuple[str, str]
"""A single button: the label shown to the user, then the callback data sent when it is pressed."""

ButtonRow = List[Button]
"""The buttons shown side by side on one row of an inline keyboard."""

Buttons = List[ButtonRow]
"""The rows of an inline keyboard, from the top one to the bottom one."""
