"""TUI plugin — Textual-based terminal user interface."""
from __future__ import annotations

from typing import Any

from open_researcher.kernel.plugin import PluginBase


class TUIPlugin(PluginBase):
    """Manages the terminal user interface using Textual.

    Subscribes to ``*`` events and projects them into a ViewModel
    for the Textual app to render.
    """

    name = "tui"
    dependencies = ["storage"]

    def __init__(self) -> None:
        self._kernel: Any = None
        self._view_model: Any = None

    async def start(self, kernel: Any) -> None:
        self._kernel = kernel

    async def stop(self) -> None:
        self._kernel = None
        self._view_model = None

    @property
    def kernel(self) -> Any:
        if self._kernel is None:
            raise RuntimeError("TUIPlugin not started")
        return self._kernel
