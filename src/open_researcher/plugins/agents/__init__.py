"""Agents plugin -- adapter registration and discovery."""
from __future__ import annotations

from typing import Type

from open_researcher.kernel.plugin import PluginBase
from open_researcher.plugins.agents.base import AgentAdapter


class AgentsPlugin(PluginBase):
    """Manages agent adapter registration and discovery."""

    name = "agents"

    def __init__(self) -> None:
        self._registry: dict[str, Type[AgentAdapter]] = {}

    async def start(self, kernel: object) -> None:  # noqa: D401
        pass

    async def stop(self) -> None:
        pass

    def register_adapter(self, cls: Type[AgentAdapter]) -> None:
        """Register an agent adapter class by its ``name``."""
        self._registry[cls.name] = cls

    def get_agent(self, name: str, config: object | None = None) -> AgentAdapter:
        """Instantiate and return the adapter registered under *name*.

        Raises ``KeyError`` if *name* is not registered.
        """
        try:
            cls = self._registry[name]
        except KeyError:
            raise KeyError(f"Agent {name!r} not registered") from None
        return cls()

    def list_agents(self) -> dict[str, Type[AgentAdapter]]:
        """Return a copy of the current adapter registry."""
        return dict(self._registry)

    def detect_agent(self) -> AgentAdapter | None:
        """Return the first adapter whose ``check_installed`` returns True."""
        for cls in self._registry.values():
            inst = cls()
            if inst.check_installed():
                return inst
        return None
