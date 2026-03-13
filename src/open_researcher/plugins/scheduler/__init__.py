"""Scheduler plugin — idea pool backed by SQLite."""
from __future__ import annotations

from typing import Any

from open_researcher.kernel.plugin import PluginBase
from open_researcher.plugins.scheduler.idea_pool import IdeaPoolStore


class SchedulerPlugin(PluginBase):
    """Manages the research idea pool and scheduling."""

    name = "scheduler"
    dependencies = ["storage"]

    def __init__(self) -> None:
        self._kernel: Any = None
        self.pool: IdeaPoolStore | None = None

    async def start(self, kernel: Any) -> None:
        self._kernel = kernel
        storage = kernel.get_plugin("storage")
        self.pool = IdeaPoolStore(storage.db)

    async def stop(self) -> None:
        self._kernel = None
        self.pool = None
