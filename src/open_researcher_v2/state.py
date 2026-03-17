"""Unified .research/ state-file access layer.

Provides a single ``ResearchState`` class that owns all reads and writes
to the six core state files under a research directory:

* ``config.yaml``   -- project configuration with defaults merging
* ``graph.json``    -- hypothesis / evidence graph (FileLock)
* ``results.tsv``   -- experiment results ledger (CSV)
* ``activity.json`` -- live worker status (FileLock)
* ``log.jsonl``     -- append-only structured log
* ``summary()``     -- aggregated snapshot for TUI consumption
"""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock

# ---------------------------------------------------------------------------
# Default schemas
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "protocol": "research-v1",
    "metrics": {
        "primary": {"name": "", "direction": ""},
    },
    "bootstrap": {
        "auto_prepare": True,
        "working_dir": ".",
        "python": "",
        "install_command": "",
        "data_command": "",
        "smoke_command": "",
    },
    "steps": {
        "understand": True,
        "literature": True,
        "plan": True,
        "execute": True,
    },
    "workers": {
        "max_parallel": 0,
        "timeout": 600,
        "max_experiments": 0,
    },
    "limits": {
        "token_budget": 0,
        "budget_policy": "warn",
        "max_crashes": 3,
    },
    "agent": {
        "worker_agent": "",
        "web_search": True,
    },
}


def _default_graph() -> dict[str, Any]:
    """Return a fresh default graph structure (always a new copy)."""
    return {
        "version": "research-v1",
        "repo_profile": {
            "profile_key": "general_code",
            "task_family": "general_code",
            "primary_metric": "",
            "direction": "",
            "source": "bootstrap",
            "resource_capabilities": {},
        },
        "hypotheses": [],
        "experiment_specs": [],
        "evidence": [],
        "claim_updates": [],
        "branch_relations": [],
        "frontier": [],
        "counters": {
            "hypothesis": 0,
            "experiment_spec": 0,
            "evidence": 0,
            "claim_update": 0,
            "branch_relation": 0,
            "frontier": 0,
            "idea": 0,
            "execution": 0,
        },
    }


_RESULTS_FIELDS = [
    "timestamp",
    "worker",
    "frontier_id",
    "status",
    "metric",
    "value",
    "description",
]

_DEFAULT_ACTIVITY: dict[str, Any] = {
    "phase": "idle",
    "paused": False,
    "skip_current": False,
    "workers": {},
    "updated_at": "",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*.

    Scalar values in *override* replace those in *base*.
    Nested dicts are merged recursively.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically (temp-file then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ResearchState
# ---------------------------------------------------------------------------


class ResearchState:
    """Unified accessor for all ``.research/`` state files.

    Parameters
    ----------
    research_dir:
        Path to the ``.research/`` directory.  Created on first write
        if it does not exist.
    """

    def __init__(self, research_dir: Path) -> None:
        self.dir = research_dir
        self._graph_lock = FileLock(str(self.dir / "graph.json.lock"), timeout=10)
        self._activity_lock = FileLock(str(self.dir / "activity.json.lock"), timeout=10)
        self._log_lock = FileLock(str(self.dir / "log.jsonl.lock"), timeout=10)
        self._results_lock = FileLock(str(self.dir / "results.tsv.lock"), timeout=10)

    # -- config.yaml --------------------------------------------------------

    def load_config(self) -> dict[str, Any]:
        """Load ``config.yaml`` merged over built-in defaults."""
        path = self.dir / "config.yaml"
        if not path.exists():
            return copy.deepcopy(_DEFAULT_CONFIG)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            return copy.deepcopy(_DEFAULT_CONFIG)
        if not isinstance(raw, dict):
            return copy.deepcopy(_DEFAULT_CONFIG)
        return _deep_merge(_DEFAULT_CONFIG, raw)

    # -- graph.json ---------------------------------------------------------

    def load_graph(self) -> dict[str, Any]:
        """Read ``graph.json`` under lock, returning defaults if absent."""
        with self._graph_lock:
            path = self.dir / "graph.json"
            if not path.exists():
                return _default_graph()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return _default_graph()
            if not isinstance(data, dict):
                return _default_graph()
            return data

    def save_graph(self, data: dict[str, Any]) -> None:
        """Write ``graph.json`` atomically under lock."""
        with self._graph_lock:
            _atomic_write(self.dir / "graph.json", json.dumps(data, indent=2))

    # -- results.tsv --------------------------------------------------------

    def load_results(self) -> list[dict[str, str]]:
        """Read ``results.tsv`` rows as a list of dicts."""
        path = self.dir / "results.tsv"
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        if not text.strip():
            return []
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        return list(reader)

    def append_result(self, row: dict[str, str]) -> None:
        """Append a single result row to ``results.tsv``.

        Creates the file with a header if it does not exist.
        """
        path = self.dir / "results.tsv"
        with self._results_lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            write_header = not path.exists() or path.stat().st_size == 0
            with open(path, "a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(
                    fh, fieldnames=_RESULTS_FIELDS, delimiter="\t",
                    extrasaction="ignore",
                )
                if write_header:
                    writer.writeheader()
                # Fill missing fields with empty strings
                complete = {f: row.get(f, "") for f in _RESULTS_FIELDS}
                if not complete["timestamp"]:
                    complete["timestamp"] = _now_iso()
                writer.writerow(complete)
                fh.flush()
                os.fsync(fh.fileno())

    # -- activity.json ------------------------------------------------------

    def load_activity(self) -> dict[str, Any]:
        """Read ``activity.json`` under lock."""
        with self._activity_lock:
            path = self.dir / "activity.json"
            if not path.exists():
                return copy.deepcopy(_DEFAULT_ACTIVITY)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return copy.deepcopy(_DEFAULT_ACTIVITY)
            if not isinstance(data, dict):
                return copy.deepcopy(_DEFAULT_ACTIVITY)
            return data

    def _save_activity(self, data: dict[str, Any]) -> None:
        """Write ``activity.json`` atomically (caller must hold lock)."""
        _atomic_write(self.dir / "activity.json", json.dumps(data, indent=2))

    def update_phase(self, phase: str) -> None:
        """Set the top-level ``phase`` in activity."""
        with self._activity_lock:
            data = self._load_activity_unlocked()
            data["phase"] = phase
            data["updated_at"] = _now_iso()
            self._save_activity(data)

    def update_worker(self, worker_id: str, **fields: Any) -> None:
        """Update or insert a worker entry in ``activity.json``."""
        with self._activity_lock:
            data = self._load_activity_unlocked()
            workers = data.get("workers", {})
            if not isinstance(workers, dict):
                workers = {}
            entry = workers.get(worker_id, {})
            entry.update(fields)
            entry["updated_at"] = _now_iso()
            workers[worker_id] = entry
            data["workers"] = workers
            data["updated_at"] = _now_iso()
            self._save_activity(data)

    def set_paused(self, paused: bool) -> None:
        """Toggle the ``paused`` flag in activity."""
        with self._activity_lock:
            data = self._load_activity_unlocked()
            data["paused"] = paused
            data["updated_at"] = _now_iso()
            self._save_activity(data)

    def set_skip_current(self, skip: bool) -> None:
        """Set the ``skip_current`` flag in activity."""
        with self._activity_lock:
            data = self._load_activity_unlocked()
            data["skip_current"] = skip
            data["updated_at"] = _now_iso()
            self._save_activity(data)

    def consume_skip(self) -> bool:
        """If ``skip_current`` is True, reset it to False and return True."""
        with self._activity_lock:
            data = self._load_activity_unlocked()
            if data.get("skip_current"):
                data["skip_current"] = False
                data["updated_at"] = _now_iso()
                self._save_activity(data)
                return True
            return False

    def _load_activity_unlocked(self) -> dict[str, Any]:
        """Read activity without acquiring lock (caller must hold it)."""
        path = self.dir / "activity.json"
        if not path.exists():
            return copy.deepcopy(_DEFAULT_ACTIVITY)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return copy.deepcopy(_DEFAULT_ACTIVITY)
        if not isinstance(data, dict):
            return copy.deepcopy(_DEFAULT_ACTIVITY)
        return data

    # -- log.jsonl ----------------------------------------------------------

    def append_log(self, entry: dict[str, Any]) -> None:
        """Append a JSON line to ``log.jsonl``."""
        record = dict(entry)
        if "timestamp" not in record:
            record["timestamp"] = _now_iso()
        line = json.dumps(record, separators=(",", ":")) + "\n"
        with self._log_lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.dir / "log.jsonl", "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())

    def tail_log(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the last *n* entries from ``log.jsonl``."""
        path = self.dir / "log.jsonl"
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    # -- summary ------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Aggregate state snapshot for TUI / status display."""
        config = self.load_config()
        graph = self.load_graph()
        results = self.load_results()
        activity = self.load_activity()

        total_experiments = len(results)
        by_status: dict[str, int] = {}
        for row in results:
            s = row.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

        frontier = graph.get("frontier", [])
        hypotheses = graph.get("hypotheses", [])

        return {
            "phase": activity.get("phase", "idle"),
            "paused": activity.get("paused", False),
            "total_experiments": total_experiments,
            "results_by_status": by_status,
            "total_hypotheses": len(hypotheses),
            "frontier_size": len(frontier),
            "workers": activity.get("workers", {}),
            "config": config,
        }
