"""Idea pool file manager with file locking for concurrent access."""

import copy
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from open_researcher.storage import atomic_write_json, locked_read_json, locked_update_json


def _default_pool() -> dict:
    return {"ideas": []}


class IdeaPool:
    """Read/write idea_pool.json with file locking."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = FileLock(str(path) + ".lock")

    # ---- low-level helpers ------------------------------------------------

    def _read_locked(self) -> dict:
        """Read idea pool JSON under lock; returns default on missing/corrupt."""
        return locked_read_json(self.path, self._lock, default=_default_pool)

    def _write(self, data: dict) -> None:
        """Atomic write (caller must already hold the lock)."""
        atomic_write_json(self.path, data)

    def _next_id(self, data: dict) -> str:
        existing = [i["id"] for i in data["ideas"]]
        n = 1
        while f"idea-{n:03d}" in existing:
            n += 1
        return f"idea-{n:03d}"

    def _atomic_update(self, updater) -> dict:
        """Lock file, read, apply updater function, write back, return updater result."""
        _data, result = locked_update_json(
            self.path, self._lock, updater, default=_default_pool
        )
        return result

    # ---- public API (signatures unchanged) --------------------------------

    def add(
        self,
        description: str,
        source: str = "original",
        category: str = "general",
        priority: int = 5,
        gpu_hint: int | str = "auto",
    ) -> dict:
        def _do(data):
            idea = {
                "id": self._next_id(data),
                "description": description,
                "source": source,
                "category": category,
                "priority": priority,
                "status": "pending",
                "gpu_hint": gpu_hint,
                "claimed_by": None,
                "assigned_experiment": None,
                "result": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            data["ideas"].append(idea)
            return idea
        return self._atomic_update(_do)

    def claim_idea(self, worker_id: str) -> dict | None:
        """Atomically claim the highest-priority pending idea for a worker."""
        def _do(data):
            pending = [i for i in data["ideas"] if i["status"] == "pending"]
            pending.sort(key=lambda x: x["priority"])
            if not pending:
                return None
            target = pending[0]
            for idea in data["ideas"]:
                if idea["id"] == target["id"]:
                    idea["status"] = "running"
                    idea["claimed_by"] = worker_id
                    break
            # 返回浅拷贝，避免调用方持有被修改后的引用
            return copy.copy(target)

        _data, result = locked_update_json(
            self.path, self._lock, _do, default=_default_pool
        )
        return result

    def list_by_status(self, status: str) -> list[dict]:
        data = self._read_locked()
        filtered = [i for i in data["ideas"] if i["status"] == status]
        filtered.sort(key=lambda x: x["priority"])
        return filtered

    def all_ideas(self) -> list[dict]:
        return self._read_locked()["ideas"]

    def update_status(self, idea_id: str, status: str, experiment: int | None = None) -> None:
        def _do(data):
            for idea in data["ideas"]:
                if idea["id"] == idea_id:
                    idea["status"] = status
                    if experiment is not None:
                        idea["assigned_experiment"] = experiment
                    break
        self._atomic_update(_do)

    def mark_done(self, idea_id: str, metric_value: float | None, verdict: str) -> None:
        def _do(data):
            for idea in data["ideas"]:
                if idea["id"] == idea_id:
                    idea["status"] = "done"
                    idea["result"] = {"metric_value": metric_value, "verdict": verdict}
                    break
        self._atomic_update(_do)

    def delete(self, idea_id: str) -> None:
        def _do(data):
            data["ideas"] = [i for i in data["ideas"] if i["id"] != idea_id]
        self._atomic_update(_do)

    def update_priority(self, idea_id: str, priority: int) -> None:
        def _do(data):
            for idea in data["ideas"]:
                if idea["id"] == idea_id:
                    idea["priority"] = priority
                    break
        self._atomic_update(_do)

    def summary(self) -> dict:
        data = self._read_locked()
        ideas = data["ideas"]
        return {
            "pending": sum(1 for i in ideas if i["status"] == "pending"),
            "running": sum(1 for i in ideas if i["status"] == "running"),
            "done": sum(1 for i in ideas if i["status"] == "done"),
            "skipped": sum(1 for i in ideas if i["status"] == "skipped"),
            "total": len(ideas),
        }
