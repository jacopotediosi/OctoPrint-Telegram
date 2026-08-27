from __future__ import annotations

from .base import FilamentPlugin
from .filamentmanager import FilamentManagerFilamentPlugin
from .spoolman import SpoolmanFilamentPlugin
from .spoolmanager import SpoolManagerFilamentPlugin

FILAMENT_PLUGINS: tuple[type[FilamentPlugin], ...] = (
    FilamentManagerFilamentPlugin,
    SpoolmanFilamentPlugin,
    SpoolManagerFilamentPlugin,
)

__all__ = ["FILAMENT_PLUGINS", "FilamentPlugin"]
