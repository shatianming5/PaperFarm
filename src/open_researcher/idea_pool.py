"""Idea pool file manager with file locking for concurrent access."""

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path


class IdeaPool:
    """Read/write idea_pool.json with file locking."""

    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict:
        if not self.path.exists():
            return {"ideas": []}
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        with open(self.path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _next_id(self, data: dict) -> str:
        existing = [i["id"] for i in data["ideas"]]
        n = 1
        while f"idea-{n:03d}" in existing:
            n += 1
        return f"idea-{n:03d}"

    def add(
        self,
        description: str,
        source: str = "original",
        category: str = "general",
        priority: int = 5,
        gpu_hint: int | str = "auto",
    ) -> dict:
        data = self._read()
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
        self._write(data)
        return idea

    def claim_idea(self, worker_id: str) -> dict | None:
        """Atomically claim the highest-priority pending idea for a worker."""
        with open(self.path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = json.loads(f.read())
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
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
                return target
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def list_by_status(self, status: str) -> list[dict]:
        data = self._read()
        filtered = [i for i in data["ideas"] if i["status"] == status]
        filtered.sort(key=lambda x: x["priority"])
        return filtered

    def all_ideas(self) -> list[dict]:
        return self._read()["ideas"]

    def update_status(self, idea_id: str, status: str, experiment: int | None = None) -> None:
        data = self._read()
        for idea in data["ideas"]:
            if idea["id"] == idea_id:
                idea["status"] = status
                if experiment is not None:
                    idea["assigned_experiment"] = experiment
                break
        self._write(data)

    def mark_done(self, idea_id: str, metric_value: float, verdict: str) -> None:
        data = self._read()
        for idea in data["ideas"]:
            if idea["id"] == idea_id:
                idea["status"] = "done"
                idea["result"] = {"metric_value": metric_value, "verdict": verdict}
                break
        self._write(data)

    def delete(self, idea_id: str) -> None:
        data = self._read()
        data["ideas"] = [i for i in data["ideas"] if i["id"] != idea_id]
        self._write(data)

    def update_priority(self, idea_id: str, priority: int) -> None:
        data = self._read()
        for idea in data["ideas"]:
            if idea["id"] == idea_id:
                idea["priority"] = priority
                break
        self._write(data)

    def summary(self) -> dict:
        data = self._read()
        ideas = data["ideas"]
        return {
            "pending": sum(1 for i in ideas if i["status"] == "pending"),
            "running": sum(1 for i in ideas if i["status"] == "running"),
            "done": sum(1 for i in ideas if i["status"] == "done"),
            "skipped": sum(1 for i in ideas if i["status"] == "skipped"),
            "total": len(ideas),
        }
