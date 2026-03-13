# Open Researcher 微内核架构重构 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Open Researcher 从 55+ 扁平模块重构为微内核 + 插件架构，统一事件总线和 SQLite 状态存储。

**Architecture:** 微内核（EventBus + PluginRegistry + EventStore）作为系统核心，9 个插件（orchestrator/agents/execution/graph/scheduler/storage/bootstrap/tui/cli）承载全部业务逻辑。插件间通过异步事件总线通信，所有状态持久化到单个 SQLite 文件 `.research/state.db`。

**Tech Stack:** Python 3.10+, asyncio, aiosqlite, Typer, Textual, pytest-asyncio

**Design Doc:** `docs/plans/2026-03-13-microkernel-architecture-design.md`

---

## Phase 0: 内核骨架

### Task 1: Event dataclass

**Files:**
- Create: `src/open_researcher/kernel/__init__.py`
- Create: `src/open_researcher/kernel/event.py`
- Test: `tests/unit/test_kernel/test_event.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_kernel/test_event.py
"""Tests for the core Event dataclass."""
import time

def test_event_creation():
    from open_researcher.kernel.event import Event

    e = Event(type="experiment.started", payload={"id": 1})
    assert e.type == "experiment.started"
    assert e.payload == {"id": 1}
    assert isinstance(e.ts, float)
    assert e.source == ""
    assert e.correlation_id == ""


def test_event_is_frozen():
    from open_researcher.kernel.event import Event

    e = Event(type="test", payload={})
    try:
        e.type = "other"
        assert False, "Should raise"
    except AttributeError:
        pass


def test_event_with_source_and_correlation():
    from open_researcher.kernel.event import Event

    e = Event(
        type="scout.completed",
        payload={"ideas": 3},
        source="orchestrator",
        correlation_id="abc-123",
    )
    assert e.source == "orchestrator"
    assert e.correlation_id == "abc-123"


def test_event_matches_exact():
    from open_researcher.kernel.event import event_matches

    e = Event(type="experiment.started", payload={})
    assert event_matches(e, "experiment.started") is True
    assert event_matches(e, "experiment.completed") is False


def test_event_matches_wildcard():
    from open_researcher.kernel.event import Event, event_matches

    e = Event(type="experiment.started", payload={})
    assert event_matches(e, "experiment.*") is True
    assert event_matches(e, "scout.*") is False
    assert event_matches(e, "*") is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_event.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/kernel/__init__.py
"""Open Researcher microkernel."""
from open_researcher.kernel.event import Event, event_matches

__all__ = ["Event", "event_matches"]
```

```python
# src/open_researcher/kernel/event.py
"""Core Event dataclass — the single message type in the system."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """Universal event carried by the EventBus.

    Attributes:
        type: Dot-namespaced event type, e.g. ``experiment.started``.
        payload: Free-form data dict.
        ts: Epoch timestamp (auto-filled).
        source: Name of the plugin that emitted the event.
        correlation_id: Tracks causal chains across events.
    """

    type: str
    payload: dict[str, Any]
    ts: float = field(default_factory=time.time)
    source: str = ""
    correlation_id: str = ""


def event_matches(event: Event, pattern: str) -> bool:
    """Check whether *event.type* matches a glob *pattern*.

    Supports ``*`` as a single-segment wildcard and ``**`` would match
    everything, but the simple ``fnmatch`` semantics are sufficient here.
    """
    return fnmatch(event.type, pattern)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_event.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/kernel/__init__.py src/open_researcher/kernel/event.py tests/unit/test_kernel/test_event.py
git commit -m "feat(kernel): add Event dataclass with wildcard matching"
```

---

### Task 2: EventStore (SQLite-backed event persistence)

**Files:**
- Create: `src/open_researcher/kernel/store.py`
- Test: `tests/unit/test_kernel/test_store.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_kernel/test_store.py
"""Tests for SQLite-backed EventStore."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_append_and_replay():
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()

    e1 = Event(type="a.one", payload={"x": 1}, source="p1")
    e2 = Event(type="b.two", payload={"y": 2}, source="p2")
    await store.append(e1)
    await store.append(e2)

    events = await store.replay()
    assert len(events) == 2
    assert events[0].type == "a.one"
    assert events[1].type == "b.two"
    await store.close()


async def test_replay_by_type():
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()

    await store.append(Event(type="experiment.started", payload={}))
    await store.append(Event(type="scout.completed", payload={}))
    await store.append(Event(type="experiment.completed", payload={}))

    events = await store.replay(type_prefix="experiment.")
    assert len(events) == 2
    assert all(e.type.startswith("experiment.") for e in events)
    await store.close()


async def test_replay_since_timestamp():
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore
    import time

    store = EventStore(":memory:")
    await store.open()

    t_before = time.time() - 10
    await store.append(Event(type="old", payload={}, ts=t_before))
    t_mid = time.time()
    await store.append(Event(type="new", payload={}, ts=t_mid + 1))

    events = await store.replay(since=t_mid)
    assert len(events) == 1
    assert events[0].type == "new"
    await store.close()


async def test_event_count():
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()
    assert await store.count() == 0

    await store.append(Event(type="a", payload={}))
    await store.append(Event(type="b", payload={}))
    assert await store.count() == 2
    await store.close()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_store.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/kernel/store.py
"""SQLite-backed event store for the microkernel."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

from open_researcher.kernel.event import Event

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    type      TEXT    NOT NULL,
    payload   TEXT    NOT NULL,
    ts        REAL    NOT NULL,
    source    TEXT    NOT NULL DEFAULT '',
    corr_id   TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts);
"""


class EventStore:
    """Append-only event log backed by SQLite.

    Parameters:
        db_path: File path or ``\":memory:\"`` for testing.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    async def open(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- write ---------------------------------------------------------------

    async def append(self, event: Event) -> None:
        assert self._conn is not None, "Store not opened"
        self._conn.execute(
            "INSERT INTO events (type, payload, ts, source, corr_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                event.type,
                json.dumps(event.payload),
                event.ts,
                event.source,
                event.correlation_id,
            ),
        )
        self._conn.commit()

    # -- read ----------------------------------------------------------------

    async def replay(
        self,
        *,
        type_prefix: str = "",
        since: float = 0.0,
    ) -> list[Event]:
        assert self._conn is not None, "Store not opened"
        clauses: list[str] = []
        params: list[object] = []
        if type_prefix:
            clauses.append("type LIKE ? || '%'")
            params.append(type_prefix)
        if since:
            clauses.append("ts > ?")
            params.append(since)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT type, payload, ts, source, corr_id FROM events{where} ORDER BY id",
            params,
        ).fetchall()
        return [
            Event(
                type=r[0],
                payload=json.loads(r[1]),
                ts=r[2],
                source=r[3],
                correlation_id=r[4],
            )
            for r in rows
        ]

    async def count(self) -> int:
        assert self._conn is not None, "Store not opened"
        row = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return row[0] if row else 0
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_store.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/kernel/store.py tests/unit/test_kernel/test_store.py
git commit -m "feat(kernel): add SQLite-backed EventStore"
```

---

### Task 3: EventBus (async event dispatch with wildcard subscriptions)

**Files:**
- Create: `src/open_researcher/kernel/bus.py`
- Test: `tests/unit/test_kernel/test_bus.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_kernel/test_bus.py
"""Tests for the async EventBus."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_emit_and_receive():
    from open_researcher.kernel.bus import EventBus
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()
    bus = EventBus(store)

    received = []
    bus.on("experiment.started", lambda e: received.append(e))

    await bus.emit(Event(type="experiment.started", payload={"id": 1}))
    await asyncio.sleep(0.05)  # let dispatch task run

    assert len(received) == 1
    assert received[0].payload == {"id": 1}
    # also persisted
    assert await store.count() == 1
    await store.close()


async def test_wildcard_subscription():
    from open_researcher.kernel.bus import EventBus
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()
    bus = EventBus(store)

    received = []
    bus.on("experiment.*", lambda e: received.append(e))

    await bus.emit(Event(type="experiment.started", payload={}))
    await bus.emit(Event(type="experiment.completed", payload={}))
    await bus.emit(Event(type="scout.completed", payload={}))
    await asyncio.sleep(0.05)

    assert len(received) == 2
    await store.close()


async def test_star_receives_all():
    from open_researcher.kernel.bus import EventBus
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()
    bus = EventBus(store)

    received = []
    bus.on("*", lambda e: received.append(e))

    await bus.emit(Event(type="a", payload={}))
    await bus.emit(Event(type="b.c", payload={}))
    await asyncio.sleep(0.05)

    assert len(received) == 2
    await store.close()


async def test_handler_error_does_not_crash_bus():
    from open_researcher.kernel.bus import EventBus
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()
    bus = EventBus(store)

    ok_received = []

    def bad_handler(e):
        raise RuntimeError("boom")

    bus.on("test", bad_handler)
    bus.on("test", lambda e: ok_received.append(e))

    await bus.emit(Event(type="test", payload={}))
    await asyncio.sleep(0.05)

    # The good handler still ran
    assert len(ok_received) == 1
    await store.close()


async def test_off_removes_handler():
    from open_researcher.kernel.bus import EventBus
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.store import EventStore

    store = EventStore(":memory:")
    await store.open()
    bus = EventBus(store)

    received = []
    handler = lambda e: received.append(e)
    bus.on("test", handler)
    bus.off("test", handler)

    await bus.emit(Event(type="test", payload={}))
    await asyncio.sleep(0.05)

    assert len(received) == 0
    await store.close()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_bus.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/kernel/bus.py
"""Async event bus with wildcard subscriptions."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable

from open_researcher.kernel.event import Event, event_matches
from open_researcher.kernel.store import EventStore

logger = logging.getLogger(__name__)

Handler = Callable[[Event], None]


class EventBus:
    """Async event bus: persist then dispatch.

    Handlers are plain sync callables invoked from an ``asyncio.Task``.
    """

    def __init__(self, store: EventStore) -> None:
        self._store = store
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    # -- subscription --------------------------------------------------------

    def on(self, pattern: str, handler: Handler) -> None:
        """Register *handler* for events matching *pattern* (glob)."""
        self._handlers[pattern].append(handler)

    def off(self, pattern: str, handler: Handler) -> None:
        """Remove a previously registered handler."""
        try:
            self._handlers[pattern].remove(handler)
        except ValueError:
            pass

    # -- emit ----------------------------------------------------------------

    async def emit(self, event: Event) -> None:
        """Persist *event* then schedule async dispatch."""
        await self._store.append(event)
        asyncio.get_running_loop().call_soon(self._dispatch_sync, event)

    # -- internal dispatch ---------------------------------------------------

    def _dispatch_sync(self, event: Event) -> None:
        for pattern, handlers in self._handlers.items():
            if event_matches(event, pattern):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        logger.exception(
                            "Handler %r failed for event %s", handler, event.type
                        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_bus.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/kernel/bus.py tests/unit/test_kernel/test_bus.py
git commit -m "feat(kernel): add async EventBus with wildcard subscriptions"
```

---

### Task 4: Plugin protocol and Registry

**Files:**
- Create: `src/open_researcher/kernel/plugin.py`
- Test: `tests/unit/test_kernel/test_plugin.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_kernel/test_plugin.py
"""Tests for the Plugin protocol and Registry."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_register_and_get_plugin():
    from open_researcher.kernel.plugin import PluginBase, Registry

    class FakePlugin(PluginBase):
        name = "fake"
        dependencies: list[str] = []

        async def start(self, kernel):
            self.started = True

        async def stop(self):
            self.stopped = True

    reg = Registry()
    plugin = FakePlugin()
    reg.register(plugin)
    assert reg.get("fake") is plugin


async def test_get_unknown_plugin_raises():
    from open_researcher.kernel.plugin import Registry

    reg = Registry()
    with pytest.raises(KeyError):
        reg.get("nonexistent")


async def test_topological_sort():
    from open_researcher.kernel.plugin import PluginBase, Registry

    class A(PluginBase):
        name = "a"
        dependencies: list[str] = []
        async def start(self, kernel): pass
        async def stop(self): pass

    class B(PluginBase):
        name = "b"
        dependencies = ["a"]
        async def start(self, kernel): pass
        async def stop(self): pass

    class C(PluginBase):
        name = "c"
        dependencies = ["b"]
        async def start(self, kernel): pass
        async def stop(self): pass

    reg = Registry()
    reg.register(C())
    reg.register(A())
    reg.register(B())

    order = reg.boot_order()
    names = [p.name for p in order]
    assert names.index("a") < names.index("b")
    assert names.index("b") < names.index("c")


async def test_circular_dependency_raises():
    from open_researcher.kernel.plugin import PluginBase, Registry

    class X(PluginBase):
        name = "x"
        dependencies = ["y"]
        async def start(self, kernel): pass
        async def stop(self): pass

    class Y(PluginBase):
        name = "y"
        dependencies = ["x"]
        async def start(self, kernel): pass
        async def stop(self): pass

    reg = Registry()
    reg.register(X())
    reg.register(Y())
    with pytest.raises(ValueError, match="[Cc]ircular"):
        reg.boot_order()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_plugin.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/kernel/plugin.py
"""Plugin protocol, base class, and dependency-aware registry."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PluginProtocol(Protocol):
    """Minimal interface every plugin must satisfy."""

    name: str
    dependencies: list[str]

    async def start(self, kernel: Any) -> None: ...
    async def stop(self) -> None: ...


class PluginBase:
    """Convenience base class implementing the protocol."""

    name: str = ""
    dependencies: list[str] = []

    async def start(self, kernel: Any) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        pass


class Registry:
    """Holds plugin instances and resolves boot order."""

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
        """Return plugins in topological (dependency) order.

        Raises ``ValueError`` on circular dependencies.
        """
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
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_plugin.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/kernel/plugin.py tests/unit/test_kernel/test_plugin.py
git commit -m "feat(kernel): add Plugin protocol and dependency-aware Registry"
```

---

### Task 5: Kernel class (ties bus + store + registry together)

**Files:**
- Create: `src/open_researcher/kernel/kernel.py`
- Modify: `src/open_researcher/kernel/__init__.py`
- Test: `tests/unit/test_kernel/test_kernel.py`
- Create: `tests/unit/test_kernel/__init__.py`
- Create: `tests/unit/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_kernel/test_kernel.py
"""Tests for the Kernel orchestrator."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_kernel_boot_and_shutdown():
    from open_researcher.kernel.kernel import Kernel
    from open_researcher.kernel.plugin import PluginBase

    started = []
    stopped = []

    class P(PluginBase):
        name = "p"
        dependencies: list[str] = []

        async def start(self, kernel):
            started.append(self.name)

        async def stop(self):
            stopped.append(self.name)

    k = Kernel(db_path=":memory:")
    await k.boot([P()])
    assert started == ["p"]

    await k.shutdown()
    assert stopped == ["p"]


async def test_kernel_emits_events():
    from open_researcher.kernel.event import Event
    from open_researcher.kernel.kernel import Kernel

    k = Kernel(db_path=":memory:")
    await k.boot([])

    received = []
    k.bus.on("test.*", lambda e: received.append(e))
    await k.bus.emit(Event(type="test.ping", payload={"msg": "hi"}))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].payload["msg"] == "hi"
    await k.shutdown()


async def test_kernel_get_plugin():
    from open_researcher.kernel.kernel import Kernel
    from open_researcher.kernel.plugin import PluginBase

    class P(PluginBase):
        name = "myplug"
        dependencies: list[str] = []
        async def start(self, kernel): pass

    k = Kernel(db_path=":memory:")
    await k.boot([P()])
    assert k.get_plugin("myplug").name == "myplug"
    await k.shutdown()


async def test_kernel_boot_respects_dependency_order():
    from open_researcher.kernel.kernel import Kernel
    from open_researcher.kernel.plugin import PluginBase

    order = []

    class A(PluginBase):
        name = "a"
        dependencies: list[str] = []
        async def start(self, kernel): order.append("a")
        async def stop(self): pass

    class B(PluginBase):
        name = "b"
        dependencies = ["a"]
        async def start(self, kernel): order.append("b")
        async def stop(self): pass

    k = Kernel(db_path=":memory:")
    await k.boot([B(), A()])
    assert order == ["a", "b"]
    await k.shutdown()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/test_kernel.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/kernel/kernel.py
"""Kernel — the microkernel that ties EventBus, EventStore, and Registry."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from open_researcher.kernel.bus import EventBus
from open_researcher.kernel.plugin import PluginProtocol, Registry
from open_researcher.kernel.store import EventStore


class Kernel:
    """Microkernel: event routing + plugin lifecycle + state persistence."""

    def __init__(self, *, db_path: str | Path = ":memory:") -> None:
        self.store = EventStore(db_path)
        self.bus = EventBus(self.store)
        self._registry = Registry()

    async def boot(self, plugins: Sequence[PluginProtocol]) -> None:
        """Open store, register plugins, start in dependency order."""
        await self.store.open()
        for p in plugins:
            self._registry.register(p)
        for p in self._registry.boot_order():
            await p.start(self)

    async def shutdown(self) -> None:
        """Stop plugins in reverse order, close store."""
        for p in reversed(self._registry.boot_order()):
            await p.stop()
        await self.store.close()

    def get_plugin(self, name: str) -> PluginProtocol:
        return self._registry.get(name)
```

Update `__init__.py`:

```python
# src/open_researcher/kernel/__init__.py
"""Open Researcher microkernel."""
from open_researcher.kernel.event import Event, event_matches
from open_researcher.kernel.kernel import Kernel
from open_researcher.kernel.bus import EventBus
from open_researcher.kernel.store import EventStore
from open_researcher.kernel.plugin import PluginBase, PluginProtocol, Registry

__all__ = [
    "Event",
    "EventBus",
    "EventStore",
    "Kernel",
    "PluginBase",
    "PluginProtocol",
    "Registry",
    "event_matches",
]
```

Create empty `__init__.py` files:

```python
# tests/unit/__init__.py
# tests/unit/test_kernel/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_kernel/ -v`
Expected: All 18 tests PASS (5 event + 4 store + 5 bus + 4 kernel)

**Step 5: Commit**

```bash
git add src/open_researcher/kernel/ tests/unit/
git commit -m "feat(kernel): add Kernel class — microkernel complete"
```

---

## Phase 1: Storage 插件 + SQLite Schema

### Task 6: SQLite schema and migrations

**Files:**
- Create: `src/open_researcher/plugins/__init__.py`
- Create: `src/open_researcher/plugins/storage/__init__.py`
- Create: `src/open_researcher/plugins/storage/models.py`
- Create: `src/open_researcher/plugins/storage/migrations.py`
- Test: `tests/unit/test_storage/__init__.py`
- Test: `tests/unit/test_storage/test_migrations.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_storage/test_migrations.py
"""Tests for SQLite schema migrations."""
import sqlite3
import pytest


def test_apply_creates_all_tables():
    from open_researcher.plugins.storage.migrations import apply_migrations

    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected = {
        "experiments",
        "hypotheses",
        "evidence",
        "ideas",
        "memory",
        "config",
        "control_commands",
        "gpu_snapshots",
        "bootstrap_state",
    }
    assert expected.issubset(tables), f"Missing: {expected - tables}"
    conn.close()


def test_apply_is_idempotent():
    from open_researcher.plugins.storage.migrations import apply_migrations

    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    apply_migrations(conn)  # second call should not raise
    conn.close()


def test_schema_version_is_set():
    from open_researcher.plugins.storage.migrations import apply_migrations

    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 1
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_storage/test_migrations.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/plugins/__init__.py
"""Open Researcher plugins."""
```

```python
# src/open_researcher/plugins/storage/__init__.py
"""Storage plugin — SQLite state management."""
```

```python
# src/open_researcher/plugins/storage/models.py
"""Table definitions as raw SQL for the state database."""

SCHEMA_V1 = """\
-- Experiment results (replaces results.tsv)
CREATE TABLE IF NOT EXISTS experiments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    hypothesis  TEXT,
    metrics     TEXT,
    started_at  REAL,
    finished_at REAL,
    worker_id   TEXT,
    metadata    TEXT
);

-- Research graph: hypotheses
CREATE TABLE IF NOT EXISTS hypotheses (
    id          TEXT PRIMARY KEY,
    claim       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'proposed',
    parent_id   TEXT,
    created_at  REAL,
    metadata    TEXT
);

-- Research graph: evidence
CREATE TABLE IF NOT EXISTS evidence (
    id            TEXT PRIMARY KEY,
    hypothesis_id TEXT REFERENCES hypotheses(id),
    experiment_id INTEGER REFERENCES experiments(id),
    direction     TEXT,
    summary       TEXT,
    created_at    REAL
);

-- Idea pool
CREATE TABLE IF NOT EXISTS ideas (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    priority    REAL DEFAULT 0,
    claimed_by  TEXT,
    created_at  REAL,
    metadata    TEXT
);

-- Research memory (key-value)
CREATE TABLE IF NOT EXISTS memory (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL
);

-- Config snapshot (key-value)
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Control commands
CREATE TABLE IF NOT EXISTS control_commands (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    source  TEXT,
    reason  TEXT,
    ts      REAL
);

-- GPU snapshots
CREATE TABLE IF NOT EXISTS gpu_snapshots (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    ts   REAL
);

-- Bootstrap state
CREATE TABLE IF NOT EXISTS bootstrap_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    ts    REAL
);
"""
```

```python
# src/open_researcher/plugins/storage/migrations.py
"""Version-tracked schema migrations for state.db."""
from __future__ import annotations

import sqlite3

from open_researcher.plugins.storage.models import SCHEMA_V1

CURRENT_VERSION = 1

# Each entry: (target_version, sql_script)
_MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations up to *CURRENT_VERSION*."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, sql in _MIGRATIONS:
        if current < target:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
            current = target
```

```python
# tests/unit/test_storage/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_storage/test_migrations.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/plugins/ tests/unit/test_storage/
git commit -m "feat(storage): add SQLite schema and migrations (v1)"
```

---

### Task 7: Database connection manager and StoragePlugin

**Files:**
- Create: `src/open_researcher/plugins/storage/db.py`
- Modify: `src/open_researcher/plugins/storage/__init__.py`
- Test: `tests/unit/test_storage/test_db.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_storage/test_db.py
"""Tests for the Database connection manager and StoragePlugin."""
import asyncio
import json
import pytest

pytestmark = pytest.mark.asyncio


async def test_db_open_and_close():
    from open_researcher.plugins.storage.db import Database

    db = Database(":memory:")
    await db.open()
    assert db.conn is not None
    await db.close()


async def test_db_insert_and_query():
    from open_researcher.plugins.storage.db import Database

    db = Database(":memory:")
    await db.open()

    db.conn.execute(
        "INSERT INTO ideas (id, title, status, priority, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("idea-1", "Test idea", "pending", 5.0, 1000.0),
    )
    db.conn.commit()

    row = db.conn.execute("SELECT title FROM ideas WHERE id = ?", ("idea-1",)).fetchone()
    assert row[0] == "Test idea"
    await db.close()


async def test_storage_plugin_lifecycle():
    from open_researcher.kernel.kernel import Kernel
    from open_researcher.plugins.storage import StoragePlugin

    plugin = StoragePlugin(db_path=":memory:")
    k = Kernel(db_path=":memory:")
    await k.boot([plugin])

    db = plugin.db
    assert db.conn is not None

    # Tables should exist
    tables = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "experiments" in tables
    assert "ideas" in tables

    await k.shutdown()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_storage/test_db.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/plugins/storage/db.py
"""SQLite connection manager for the state database."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from open_researcher.plugins.storage.migrations import apply_migrations


class Database:
    """Thin wrapper around a sqlite3 connection with auto-migration."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self.conn: sqlite3.Connection | None = None

    async def open(self) -> None:
        self.conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(self.conn)

    async def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
```

Update `src/open_researcher/plugins/storage/__init__.py`:

```python
# src/open_researcher/plugins/storage/__init__.py
"""Storage plugin — SQLite state management."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_researcher.kernel.plugin import PluginBase
from open_researcher.plugins.storage.db import Database


class StoragePlugin(PluginBase):
    """Manages the SQLite state database lifecycle."""

    name = "storage"
    dependencies: list[str] = []

    def __init__(self, *, db_path: str | Path = ".research/state.db") -> None:
        self._db_path = db_path
        self.db = Database(db_path)

    async def start(self, kernel: Any) -> None:
        await self.db.open()

    async def stop(self) -> None:
        await self.db.close()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_storage/ -v`
Expected: All 6 tests PASS (3 migrations + 3 db)

**Step 5: Commit**

```bash
git add src/open_researcher/plugins/storage/ tests/unit/test_storage/
git commit -m "feat(storage): add Database manager and StoragePlugin"
```

---

## Phase 2: Graph 插件

### Task 8: Graph plugin — hypotheses and evidence in SQLite

**Files:**
- Create: `src/open_researcher/plugins/graph/__init__.py`
- Create: `src/open_researcher/plugins/graph/store.py`
- Test: `tests/unit/test_graph/__init__.py`
- Test: `tests/unit/test_graph/test_graph_store.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_graph/test_graph_store.py
"""Tests for the Graph SQLite store."""
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def graph_store():
    from open_researcher.plugins.storage.db import Database
    from open_researcher.plugins.graph.store import GraphStore

    db = Database(":memory:")
    await db.open()
    store = GraphStore(db)
    yield store
    await db.close()


async def test_add_hypothesis(graph_store):
    h = await graph_store.add_hypothesis(
        id="h-001",
        claim="Larger batch size improves accuracy",
        status="proposed",
    )
    assert h["id"] == "h-001"
    assert h["status"] == "proposed"


async def test_get_hypothesis(graph_store):
    await graph_store.add_hypothesis(id="h-001", claim="Test", status="proposed")
    h = await graph_store.get_hypothesis("h-001")
    assert h is not None
    assert h["claim"] == "Test"


async def test_get_missing_hypothesis_returns_none(graph_store):
    h = await graph_store.get_hypothesis("nonexistent")
    assert h is None


async def test_update_hypothesis_status(graph_store):
    await graph_store.add_hypothesis(id="h-001", claim="Test", status="proposed")
    await graph_store.update_hypothesis("h-001", status="testing")
    h = await graph_store.get_hypothesis("h-001")
    assert h["status"] == "testing"


async def test_list_hypotheses(graph_store):
    await graph_store.add_hypothesis(id="h-001", claim="A", status="proposed")
    await graph_store.add_hypothesis(id="h-002", claim="B", status="testing")
    all_h = await graph_store.list_hypotheses()
    assert len(all_h) == 2
    proposed = await graph_store.list_hypotheses(status="proposed")
    assert len(proposed) == 1


async def test_add_and_list_evidence(graph_store):
    await graph_store.add_hypothesis(id="h-001", claim="Test", status="proposed")
    await graph_store.add_evidence(
        id="ev-001",
        hypothesis_id="h-001",
        experiment_id=1,
        direction="supports",
        summary="Accuracy improved by 5%",
    )
    evs = await graph_store.list_evidence(hypothesis_id="h-001")
    assert len(evs) == 1
    assert evs[0]["direction"] == "supports"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_graph/test_graph_store.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/plugins/graph/__init__.py
"""Graph plugin — research hypothesis/evidence graph."""
```

```python
# src/open_researcher/plugins/graph/store.py
"""SQLite-backed graph store for hypotheses and evidence."""
from __future__ import annotations

import json
import time
from typing import Any

from open_researcher.plugins.storage.db import Database


class GraphStore:
    """CRUD for hypotheses and evidence tables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def _conn(self):
        assert self._db.conn is not None
        return self._db.conn

    # -- hypotheses ----------------------------------------------------------

    async def add_hypothesis(
        self,
        *,
        id: str,
        claim: str,
        status: str = "proposed",
        parent_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        self._conn.execute(
            "INSERT INTO hypotheses (id, claim, status, parent_id, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (id, claim, status, parent_id, now, json.dumps(metadata or {})),
        )
        self._conn.commit()
        return {"id": id, "claim": claim, "status": status, "parent_id": parent_id, "created_at": now}

    async def get_hypothesis(self, id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, claim, status, parent_id, created_at, metadata FROM hypotheses WHERE id = ?",
            (id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "claim": row[1], "status": row[2],
            "parent_id": row[3], "created_at": row[4],
            "metadata": json.loads(row[5]) if row[5] else {},
        }

    async def update_hypothesis(self, id: str, **fields: Any) -> None:
        sets = []
        params = []
        for k, v in fields.items():
            sets.append(f"{k} = ?")
            params.append(v)
        params.append(id)
        self._conn.execute(
            f"UPDATE hypotheses SET {', '.join(sets)} WHERE id = ?", params
        )
        self._conn.commit()

    async def list_hypotheses(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT id, claim, status, parent_id, created_at FROM hypotheses WHERE status = ?",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, claim, status, parent_id, created_at FROM hypotheses"
            ).fetchall()
        return [
            {"id": r[0], "claim": r[1], "status": r[2], "parent_id": r[3], "created_at": r[4]}
            for r in rows
        ]

    # -- evidence ------------------------------------------------------------

    async def add_evidence(
        self,
        *,
        id: str,
        hypothesis_id: str,
        experiment_id: int | None = None,
        direction: str = "neutral",
        summary: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        self._conn.execute(
            "INSERT INTO evidence (id, hypothesis_id, experiment_id, direction, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (id, hypothesis_id, experiment_id, direction, summary, now),
        )
        self._conn.commit()
        return {"id": id, "hypothesis_id": hypothesis_id, "direction": direction, "created_at": now}

    async def list_evidence(self, *, hypothesis_id: str | None = None) -> list[dict[str, Any]]:
        if hypothesis_id:
            rows = self._conn.execute(
                "SELECT id, hypothesis_id, experiment_id, direction, summary, created_at "
                "FROM evidence WHERE hypothesis_id = ?",
                (hypothesis_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, hypothesis_id, experiment_id, direction, summary, created_at FROM evidence"
            ).fetchall()
        return [
            {"id": r[0], "hypothesis_id": r[1], "experiment_id": r[2],
             "direction": r[3], "summary": r[4], "created_at": r[5]}
            for r in rows
        ]
```

```python
# tests/unit/test_graph/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_graph/ -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/plugins/graph/ tests/unit/test_graph/
git commit -m "feat(graph): add SQLite-backed hypothesis/evidence store"
```

---

## Phase 3: Scheduler 插件

### Task 9: Idea pool in SQLite

**Files:**
- Create: `src/open_researcher/plugins/scheduler/__init__.py`
- Create: `src/open_researcher/plugins/scheduler/idea_pool.py`
- Test: `tests/unit/test_scheduler/__init__.py`
- Test: `tests/unit/test_scheduler/test_idea_pool.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_scheduler/test_idea_pool.py
"""Tests for the SQLite-backed idea pool."""
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pool():
    from open_researcher.plugins.storage.db import Database
    from open_researcher.plugins.scheduler.idea_pool import IdeaPoolStore

    db = Database(":memory:")
    await db.open()
    store = IdeaPoolStore(db)
    yield store
    await db.close()


async def test_add_idea(pool):
    idea = await pool.add(title="Try larger batch size", priority=5)
    assert idea["id"].startswith("idea-")
    assert idea["status"] == "pending"


async def test_list_pending(pool):
    await pool.add(title="A", priority=3)
    await pool.add(title="B", priority=7)
    pending = await pool.list_by_status("pending")
    assert len(pending) == 2


async def test_claim_idea(pool):
    await pool.add(title="A", priority=5)
    claimed = await pool.claim(worker_id="w-1")
    assert claimed is not None
    assert claimed["status"] == "claimed"
    assert claimed["claimed_by"] == "w-1"

    # Nothing left to claim
    second = await pool.claim(worker_id="w-2")
    assert second is None


async def test_complete_idea(pool):
    idea = await pool.add(title="A", priority=5)
    await pool.claim(worker_id="w-1")
    await pool.complete(idea["id"])
    result = await pool.get(idea["id"])
    assert result["status"] == "done"


async def test_claim_respects_priority(pool):
    await pool.add(title="Low", priority=1)
    await pool.add(title="High", priority=10)
    claimed = await pool.claim(worker_id="w-1")
    assert claimed["title"] == "High"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_scheduler/test_idea_pool.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/plugins/scheduler/__init__.py
"""Scheduler plugin — resource scheduling, idea pool, memory."""
```

```python
# src/open_researcher/plugins/scheduler/idea_pool.py
"""SQLite-backed idea pool with atomic claim support."""
from __future__ import annotations

import json
import time
from typing import Any

from open_researcher.plugins.storage.db import Database


class IdeaPoolStore:
    """CRUD + claim semantics for the ideas table."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._counter = 0

    @property
    def _conn(self):
        assert self._db.conn is not None
        return self._db.conn

    def _next_id(self) -> str:
        self._counter += 1
        return f"idea-{self._counter:03d}"

    async def add(
        self,
        *,
        title: str,
        priority: float = 0,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        id = self._next_id()
        now = time.time()
        self._conn.execute(
            "INSERT INTO ideas (id, title, status, priority, created_at, metadata) "
            "VALUES (?, ?, 'pending', ?, ?, ?)",
            (id, title, priority, now, json.dumps(metadata or {})),
        )
        self._conn.commit()
        return {"id": id, "title": title, "status": "pending", "priority": priority, "created_at": now}

    async def get(self, id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, title, status, priority, claimed_by, created_at, metadata "
            "FROM ideas WHERE id = ?",
            (id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "title": row[1], "status": row[2],
            "priority": row[3], "claimed_by": row[4], "created_at": row[5],
            "metadata": json.loads(row[6]) if row[6] else {},
        }

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, title, status, priority, claimed_by, created_at "
            "FROM ideas WHERE status = ? ORDER BY priority DESC",
            (status,),
        ).fetchall()
        return [
            {"id": r[0], "title": r[1], "status": r[2],
             "priority": r[3], "claimed_by": r[4], "created_at": r[5]}
            for r in rows
        ]

    async def claim(self, *, worker_id: str) -> dict[str, Any] | None:
        """Atomically claim the highest-priority pending idea."""
        row = self._conn.execute(
            "SELECT id, title, priority FROM ideas "
            "WHERE status = 'pending' ORDER BY priority DESC LIMIT 1",
        ).fetchone()
        if not row:
            return None
        idea_id, title, priority = row
        self._conn.execute(
            "UPDATE ideas SET status = 'claimed', claimed_by = ? WHERE id = ? AND status = 'pending'",
            (worker_id, idea_id),
        )
        self._conn.commit()
        return {"id": idea_id, "title": title, "status": "claimed", "claimed_by": worker_id, "priority": priority}

    async def complete(self, id: str) -> None:
        self._conn.execute("UPDATE ideas SET status = 'done' WHERE id = ?", (id,))
        self._conn.commit()

    async def skip(self, id: str) -> None:
        self._conn.execute("UPDATE ideas SET status = 'skipped' WHERE id = ?", (id,))
        self._conn.commit()
```

```python
# tests/unit/test_scheduler/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_scheduler/ -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/plugins/scheduler/ tests/unit/test_scheduler/
git commit -m "feat(scheduler): add SQLite-backed idea pool with claim semantics"
```

---

## Phase 4: Agents 插件

### Task 10: Agent adapter protocol and plugin shell

**Files:**
- Create: `src/open_researcher/plugins/agents/__init__.py`
- Create: `src/open_researcher/plugins/agents/base.py`
- Test: `tests/unit/test_agents/__init__.py`
- Test: `tests/unit/test_agents/test_agent_base.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_agents/test_agent_base.py
"""Tests for the agent adapter protocol."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_fake_agent_conforms_to_protocol():
    from open_researcher.plugins.agents.base import AgentAdapter

    class FakeAgent(AgentAdapter):
        name = "fake"

        def check_installed(self) -> bool:
            return True

        def run(self, repo_path, program_file, *, on_output=None, env=None):
            return 0

        def terminate(self):
            pass

    agent = FakeAgent()
    assert agent.name == "fake"
    assert agent.check_installed() is True
    assert agent.run("/tmp", "test.md") == 0


async def test_agents_plugin_registers_and_discovers():
    from open_researcher.plugins.agents import AgentsPlugin
    from open_researcher.plugins.agents.base import AgentAdapter
    from open_researcher.kernel.kernel import Kernel

    class FakeAgent(AgentAdapter):
        name = "fake"
        def check_installed(self) -> bool: return True
        def run(self, repo_path, program_file, **kw): return 0
        def terminate(self): pass

    plugin = AgentsPlugin()
    plugin.register_adapter(FakeAgent)

    k = Kernel(db_path=":memory:")
    await k.boot([plugin])

    agent = plugin.get_agent("fake")
    assert agent.name == "fake"

    with pytest.raises(KeyError):
        plugin.get_agent("nonexistent")

    await k.shutdown()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_agents/test_agent_base.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/open_researcher/plugins/agents/base.py
"""Agent adapter protocol — the interface every AI agent must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable


class AgentAdapter(ABC):
    """Base class for AI agent adapters (Claude Code, Codex, Aider, etc.)."""

    name: str = ""

    @abstractmethod
    def check_installed(self) -> bool:
        """Return True if this agent's CLI is available on the system."""
        ...

    @abstractmethod
    def run(
        self,
        repo_path: str | Path,
        program_file: str | Path,
        *,
        on_output: Callable[[str], None] | None = None,
        env: dict[str, str] | None = None,
    ) -> int:
        """Run the agent on *program_file* and return the exit code."""
        ...

    @abstractmethod
    def terminate(self) -> None:
        """Terminate a running agent."""
        ...
```

```python
# src/open_researcher/plugins/agents/__init__.py
"""Agents plugin — registry and lifecycle for AI agent adapters."""
from __future__ import annotations

from typing import Any

from open_researcher.kernel.plugin import PluginBase
from open_researcher.plugins.agents.base import AgentAdapter


class AgentsPlugin(PluginBase):
    """Manages agent adapter registration and discovery."""

    name = "agents"
    dependencies: list[str] = []

    def __init__(self) -> None:
        self._registry: dict[str, type[AgentAdapter]] = {}

    async def start(self, kernel: Any) -> None:
        pass

    async def stop(self) -> None:
        pass

    def register_adapter(self, cls: type[AgentAdapter]) -> None:
        self._registry[cls.name] = cls

    def get_agent(self, name: str, config: dict | None = None) -> AgentAdapter:
        try:
            cls = self._registry[name]
        except KeyError:
            raise KeyError(f"Agent {name!r} not registered") from None
        return cls()

    def list_agents(self) -> dict[str, type[AgentAdapter]]:
        return dict(self._registry)

    def detect_agent(self) -> AgentAdapter | None:
        for cls in self._registry.values():
            instance = cls()
            if instance.check_installed():
                return instance
        return None
```

```python
# tests/unit/test_agents/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/unit/test_agents/ -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/plugins/agents/ tests/unit/test_agents/
git commit -m "feat(agents): add AgentAdapter protocol and AgentsPlugin"
```

---

## Phase 5: 集成测试 — 多插件协作

### Task 11: Integration test — kernel boots with storage + graph + scheduler + agents

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_kernel_integration.py`

**Step 1: Write the test**

```python
# tests/integration/test_kernel_integration.py
"""Integration tests: multiple plugins cooperating through the kernel."""
import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def test_full_kernel_boot_with_plugins():
    """All core plugins boot, communicate via events, and shutdown cleanly."""
    from open_researcher.kernel import Kernel, Event
    from open_researcher.plugins.storage import StoragePlugin
    from open_researcher.plugins.agents import AgentsPlugin

    storage = StoragePlugin(db_path=":memory:")
    agents = AgentsPlugin()

    k = Kernel(db_path=":memory:")
    await k.boot([storage, agents])

    # Emit an event and verify it persists
    await k.bus.emit(Event(type="test.ping", payload={"msg": "hello"}, source="test"))
    events = await k.store.replay()
    assert any(e.type == "test.ping" for e in events)

    # Storage tables exist
    tables = {
        row[0]
        for row in storage.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "experiments" in tables
    assert "ideas" in tables
    assert "hypotheses" in tables

    await k.shutdown()


async def test_event_flow_between_plugins():
    """Verify events emitted by one plugin are received by another."""
    from open_researcher.kernel import Kernel, Event, PluginBase

    received_events = []

    class ProducerPlugin(PluginBase):
        name = "producer"
        dependencies: list[str] = []

        async def start(self, kernel):
            self._kernel = kernel

        async def produce(self):
            await self._kernel.bus.emit(
                Event(type="data.ready", payload={"rows": 42}, source=self.name)
            )

    class ConsumerPlugin(PluginBase):
        name = "consumer"
        dependencies = ["producer"]

        async def start(self, kernel):
            kernel.bus.on("data.*", lambda e: received_events.append(e))

    producer = ProducerPlugin()
    consumer = ConsumerPlugin()

    k = Kernel(db_path=":memory:")
    await k.boot([consumer, producer])

    await producer.produce()
    await asyncio.sleep(0.05)

    assert len(received_events) == 1
    assert received_events[0].payload["rows"] == 42

    await k.shutdown()


async def test_graph_store_with_storage_plugin():
    """GraphStore uses the StoragePlugin's database."""
    from open_researcher.kernel import Kernel
    from open_researcher.plugins.storage import StoragePlugin
    from open_researcher.plugins.graph.store import GraphStore

    storage = StoragePlugin(db_path=":memory:")
    k = Kernel(db_path=":memory:")
    await k.boot([storage])

    graph = GraphStore(storage.db)
    await graph.add_hypothesis(id="h-1", claim="Test", status="proposed")
    h = await graph.get_hypothesis("h-1")
    assert h["claim"] == "Test"

    await k.shutdown()


async def test_idea_pool_with_storage_plugin():
    """IdeaPoolStore uses the StoragePlugin's database."""
    from open_researcher.kernel import Kernel
    from open_researcher.plugins.storage import StoragePlugin
    from open_researcher.plugins.scheduler.idea_pool import IdeaPoolStore

    storage = StoragePlugin(db_path=":memory:")
    k = Kernel(db_path=":memory:")
    await k.boot([storage])

    pool = IdeaPoolStore(storage.db)
    idea = await pool.add(title="Test idea", priority=5)
    claimed = await pool.claim(worker_id="w-1")
    assert claimed["id"] == idea["id"]

    await k.shutdown()
```

**Step 2: Run test**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/integration/ -v`
Expected: All 4 tests PASS

**Step 3: Commit**

```bash
git add tests/integration/
git commit -m "test: add kernel integration tests for multi-plugin cooperation"
```

---

## Phase 6-8: 剩余插件（概要）

> 以下 Phase 的具体 Task 在 Phase 0-5 完成且验证后再细化。
> 每个 Phase 遵循同样的 TDD 模式：写测试 → 失败 → 实现 → 通过 → 提交。

### Task 12: Orchestrator plugin — 迁移 research_loop.py

**Files:**
- Create: `src/open_researcher/plugins/orchestrator/__init__.py`
- Create: `src/open_researcher/plugins/orchestrator/loop.py`
- Create: `src/open_researcher/plugins/orchestrator/phases.py`
- Create: `src/open_researcher/plugins/orchestrator/safety.py`
- Test: `tests/unit/test_orchestrator/`

**Scope:**
- 将 `research_loop.py` 的 `ResearchLoop` 拆分为事件驱动的插件
- `loop.py`: 主编排逻辑，监听 `bootstrap.completed`，驱动 Scout→Manager→Critic→Experiment
- `phases.py`: 各阶段独立函数（`run_scout`, `run_manager_cycle`, `run_critic`, `run_experiment_batch`）
- `safety.py`: 从 `crash_counter.py`, `git_safety.py` 提取安全检查逻辑
- 通过 `kernel.bus.emit()` 替代原有的 `self.emit()` 回调

### Task 13: Execution plugin — 迁移 worker.py + gpu_manager.py

**Files:**
- Create: `src/open_researcher/plugins/execution/__init__.py`
- Create: `src/open_researcher/plugins/execution/worker.py`
- Create: `src/open_researcher/plugins/execution/parallel.py`
- Create: `src/open_researcher/plugins/execution/worktree.py`
- Create: `src/open_researcher/plugins/execution/gpu.py`
- Test: `tests/unit/test_execution/`

**Scope:**
- 合并 `gpu_manager.py` (541行) + `worker_plugins.py` 中 GPU 部分 → `gpu.py`
- `worker.py`: 从原 `worker.py` (1370行) 提取 Worker 生命周期
- `parallel.py`: 从 `parallel_runtime.py` (236行) 迁移批处理运行器
- `worktree.py`: 从 `worktree.py` (402行) 迁移 Git worktree 隔离

### Task 14: Bootstrap plugin — 迁移 bootstrap.py

**Files:**
- Create: `src/open_researcher/plugins/bootstrap/__init__.py`
- Create: `src/open_researcher/plugins/bootstrap/detection.py`
- Create: `src/open_researcher/plugins/bootstrap/prepare.py`
- Move: `src/open_researcher/templates/` → `src/open_researcher/plugins/bootstrap/templates/`
- Test: `tests/unit/test_bootstrap/`

**Scope:**
- 将 `bootstrap.py` (953行) 拆分为检测和执行两部分
- `detection.py`: 仓库类型检测、Python 环境解析、命令检测
- `prepare.py`: 准备命令执行、状态管理
- 监听 `run.requested` 事件，发出 `bootstrap.*` 事件

### Task 15: CLI plugin — 迁移 cli.py + *_cmd.py

**Files:**
- Create: `src/open_researcher/plugins/cli/__init__.py`
- Create: `src/open_researcher/plugins/cli/main.py`
- Create: `src/open_researcher/plugins/cli/run.py`
- Create: `src/open_researcher/plugins/cli/status.py`
- Create: `src/open_researcher/plugins/cli/results.py`
- Create: `src/open_researcher/plugins/cli/doctor.py`
- Create: `src/open_researcher/plugins/cli/export.py`
- Test: `tests/unit/test_cli/`

**Scope:**
- `main.py`: Typer app 定义 + 插件引导
- 各子命令文件保持 Typer 命令注册，内部通过 `kernel.bus.emit()` 触发工作流
- 更新 `pyproject.toml` 入口点

### Task 16: TUI plugin — 迁移 tui/

**Files:**
- Create: `src/open_researcher/plugins/tui/__init__.py`
- Create: `src/open_researcher/plugins/tui/app.py`
- Create: `src/open_researcher/plugins/tui/view_model.py`
- Create: `src/open_researcher/plugins/tui/panels.py`
- Create: `src/open_researcher/plugins/tui/tables.py`
- Create: `src/open_researcher/plugins/tui/modals.py`
- Test: `tests/unit/test_tui/`

**Scope:**
- 拆分 `tui/widgets.py` (1619行) 为 `panels.py` + `tables.py` + `modals.py`
- `view_model.py`: 监听 `*` 事件，投影到 TUI 状态
- `app.py`: Textual 主应用，从 view_model 读取状态渲染

---

## Phase 9: 清理

### Task 17: Update pyproject.toml entry points

**Files:**
- Modify: `pyproject.toml`

**Scope:**
- 添加 `[project.entry-points."open_researcher.plugins"]` 段
- 更新 `[project.scripts]` 入口点指向新 CLI
- 添加 `aiosqlite` 依赖（如果选择异步 SQLite）

### Task 18: Delete old flat modules

**Scope:**
- 删除 `src/open_researcher/` 下已迁移的旧模块（research_events.py, storage.py, research_loop.py 等）
- 运行完整测试套件确保无回归
- 更新所有 import 路径

### Task 19: Final integration test — end-to-end headless run

**Files:**
- Create: `tests/integration/test_headless_e2e.py`

**Scope:**
- 使用内存数据库 + mock agent 执行完整的 Scout→Manager→Critic→Experiment 循环
- 验证所有事件按预期顺序发出
- 验证 SQLite 中的状态正确持久化

---

## 注意事项

1. **Phase 0-5 为基础设施阶段**，必须先完成才能开始 Phase 6-8
2. **Phase 6-8 可以并行开发**（各插件通过事件接口解耦）
3. **每个 Task 结束后都要运行完整测试套件** 确保无回归：`python -m pytest tests/ -v`
4. **旧代码在 Phase 9 之前不删除**，新旧代码可以共存
5. 现有的 52 个测试文件在迁移期间保持可运行状态
