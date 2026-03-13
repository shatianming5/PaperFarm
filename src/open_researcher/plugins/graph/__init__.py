"""Graph plugin — hypothesis/evidence tracking for Open Researcher."""
from __future__ import annotations

from typing import Any

from open_researcher.kernel.plugin import PluginBase
from open_researcher.plugins.graph.store import GraphStore


class GraphPlugin(PluginBase):
    """Manages the research hypothesis/evidence graph."""

    name = "graph"
    dependencies = ["storage"]

    def __init__(self) -> None:
        self._kernel: Any = None
        self.store: GraphStore | None = None

    async def start(self, kernel: Any) -> None:
        self._kernel = kernel
        storage = kernel.get_plugin("storage")
        self.store = GraphStore(storage.db)

    async def stop(self) -> None:
        self._kernel = None
        self.store = None
