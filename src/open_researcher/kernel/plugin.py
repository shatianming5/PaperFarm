"""Plugin protocol, base class, and dependency-aware registry."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PluginProtocol(Protocol):
    name: str
    dependencies: list[str]

    async def start(self, kernel: Any) -> None: ...
    async def stop(self) -> None: ...


class PluginBase:
    name: str = ""
    dependencies: list[str] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Prevent shared mutable default: each subclass gets its own list.
        if "dependencies" not in cls.__dict__:
            cls.dependencies = []

    async def start(self, kernel: Any) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        pass


class Registry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginProtocol] = {}

    def register(self, plugin: PluginProtocol) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> PluginProtocol:
        try:
            return self._plugins[name]
        except KeyError:
            raise KeyError(f"Plugin {name!r} not registered") from None

    def all(self) -> list[PluginProtocol]:
        return list(self._plugins.values())

    def boot_order(self) -> list[PluginProtocol]:
        visited: set[str] = set()
        order: list[str] = []
        visiting: set[str] = set()

        def _visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving {name!r}")
            visiting.add(name)
            plugin = self._plugins.get(name)
            if plugin:
                for dep in plugin.dependencies:
                    _visit(dep)
            visiting.discard(name)
            visited.add(name)
            order.append(name)

        for name in self._plugins:
            _visit(name)

        return [self._plugins[n] for n in order if n in self._plugins]
