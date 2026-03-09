# Multi-Agent + Interactive TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single-agent Rich Live TUI with a dual-agent (Idea + Experiment) architecture and a Textual-based interactive terminal UI with full keyboard control, GPU management, and file-based agent coordination.

**Architecture:** Two AI agent subprocesses (Idea Agent, Experiment Agent) run in parallel, coordinating via shared JSON files (`idea_pool.json`, `activity.json`, `control.json`). A Textual TUI app polls these files to display real-time status and accepts keyboard input to control the agents. GPU allocation supports both local multi-GPU and remote SSH hosts.

**Tech Stack:** Python 3.10+, Textual (TUI framework), Typer (CLI), Jinja2 (templates), PyYAML, fcntl (file locking)

---

## Task 1: Add `textual` dependency and remove `fastapi`/`uvicorn`

**Files:**
- Modify: `pyproject.toml:30-37`

**Step 1: Update pyproject.toml dependencies**

Replace the dependencies block:
```toml
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
    "textual>=0.85.0",
]
```

Remove `fastapi` and `uvicorn` from dependencies. Remove `httpx` from dev dependencies (was for dashboard tests).

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4.0",
]
```

**Step 2: Install updated dependencies**

Run: `pip install -e ".[dev]"`
Expected: textual installed, fastapi/uvicorn no longer required

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: replace fastapi/uvicorn with textual dependency"
```

---

## Task 2: Create `idea_pool.py` — IdeaPool file manager with locking

**Files:**
- Create: `src/open_researcher/idea_pool.py`
- Create: `tests/test_idea_pool.py`

**Step 1: Write failing tests**

```python
# tests/test_idea_pool.py
"""Tests for idea pool file manager."""

import json
from pathlib import Path

import pytest

from open_researcher.idea_pool import IdeaPool


@pytest.fixture
def pool_file(tmp_path):
    p = tmp_path / "idea_pool.json"
    p.write_text(json.dumps({"ideas": []}))
    return p


@pytest.fixture
def pool(pool_file):
    return IdeaPool(pool_file)


def test_add_idea(pool, pool_file):
    pool.add("cosine LR with warmup", source="literature", category="lr_schedule", priority=1)
    data = json.loads(pool_file.read_text())
    assert len(data["ideas"]) == 1
    idea = data["ideas"][0]
    assert idea["description"] == "cosine LR with warmup"
    assert idea["status"] == "pending"
    assert idea["priority"] == 1
    assert idea["id"].startswith("idea-")


def test_list_by_status(pool):
    pool.add("idea A", priority=2)
    pool.add("idea B", priority=1)
    pending = pool.list_by_status("pending")
    assert len(pending) == 2
    # Sorted by priority ascending
    assert pending[0]["description"] == "idea B"


def test_update_status(pool):
    pool.add("idea A", priority=1)
    ideas = pool.list_by_status("pending")
    pool.update_status(ideas[0]["id"], "running", experiment=1)
    running = pool.list_by_status("running")
    assert len(running) == 1
    assert running[0]["assigned_experiment"] == 1


def test_mark_done(pool):
    pool.add("idea A", priority=1)
    ideas = pool.list_by_status("pending")
    pool.mark_done(ideas[0]["id"], metric_value=1.49, verdict="kept")
    done = pool.list_by_status("done")
    assert len(done) == 1
    assert done[0]["result"]["metric_value"] == 1.49


def test_summary(pool):
    pool.add("A", priority=1)
    pool.add("B", priority=2)
    pool.add("C", priority=3)
    ideas = pool.list_by_status("pending")
    pool.update_status(ideas[0]["id"], "running")
    s = pool.summary()
    assert s == {"pending": 2, "running": 1, "done": 0, "skipped": 0, "total": 3}


def test_delete_idea(pool):
    pool.add("A", priority=1)
    ideas = pool.list_by_status("pending")
    pool.delete(ideas[0]["id"])
    assert pool.summary()["total"] == 0


def test_update_priority(pool):
    pool.add("A", priority=3)
    ideas = pool.list_by_status("pending")
    pool.update_priority(ideas[0]["id"], 1)
    reloaded = pool.list_by_status("pending")
    assert reloaded[0]["priority"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_idea_pool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'open_researcher.idea_pool'`

**Step 3: Write implementation**

```python
# src/open_researcher/idea_pool.py
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
    ) -> dict:
        data = self._read()
        idea = {
            "id": self._next_id(data),
            "description": description,
            "source": source,
            "category": category,
            "priority": priority,
            "status": "pending",
            "assigned_experiment": None,
            "result": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        data["ideas"].append(idea)
        self._write(data)
        return idea

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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_idea_pool.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/idea_pool.py tests/test_idea_pool.py
git commit -m "feat: add IdeaPool file manager with locking"
```

---

## Task 3: Create `activity.py` — ActivityMonitor for agent status tracking

**Files:**
- Create: `src/open_researcher/activity.py`
- Create: `tests/test_activity.py`

**Step 1: Write failing tests**

```python
# tests/test_activity.py
"""Tests for activity monitor."""

import json
import time
from pathlib import Path

import pytest

from open_researcher.activity import ActivityMonitor


@pytest.fixture
def research_dir(tmp_path):
    d = tmp_path / ".research"
    d.mkdir()
    return d


@pytest.fixture
def monitor(research_dir):
    return ActivityMonitor(research_dir)


def test_update_and_get(monitor, research_dir):
    monitor.update("idea_agent", status="analyzing", detail="reviewing #7")
    activity = monitor.get("idea_agent")
    assert activity["status"] == "analyzing"
    assert activity["detail"] == "reviewing #7"
    assert "updated_at" in activity


def test_get_missing_agent(monitor):
    assert monitor.get("nonexistent") is None


def test_update_experiment_agent(monitor):
    monitor.update(
        "experiment_agent",
        status="evaluating",
        idea="cosine LR",
        experiment=8,
        gpu={"host": "local", "device": 0},
        branch="exp/cosine-lr",
    )
    act = monitor.get("experiment_agent")
    assert act["status"] == "evaluating"
    assert act["gpu"]["device"] == 0


def test_get_all(monitor):
    monitor.update("idea_agent", status="idle")
    monitor.update("experiment_agent", status="coding")
    all_act = monitor.get_all()
    assert "idea_agent" in all_act
    assert "experiment_agent" in all_act
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_activity.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/open_researcher/activity.py
"""Activity monitor — track real-time agent status via activity.json."""

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path


class ActivityMonitor:
    """Read/write activity.json for agent status tracking."""

    def __init__(self, research_dir: Path):
        self.path = research_dir / "activity.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict) -> None:
        with open(self.path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def update(self, agent_key: str, **kwargs) -> None:
        data = self._read()
        entry = data.get(agent_key, {})
        entry.update(kwargs)
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        data[agent_key] = entry
        self._write(data)

    def get(self, agent_key: str) -> dict | None:
        data = self._read()
        return data.get(agent_key)

    def get_all(self) -> dict:
        return self._read()
```

**Step 4: Run tests**

Run: `pytest tests/test_activity.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/activity.py tests/test_activity.py
git commit -m "feat: add ActivityMonitor for agent status tracking"
```

---

## Task 4: Create `gpu_manager.py` — GPU detection, allocation, and release

**Files:**
- Create: `src/open_researcher/gpu_manager.py`
- Create: `tests/test_gpu_manager.py`

**Step 1: Write failing tests**

```python
# tests/test_gpu_manager.py
"""Tests for GPU manager."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from open_researcher.gpu_manager import GPUManager


@pytest.fixture
def gpu_file(tmp_path):
    return tmp_path / "gpu_status.json"


@pytest.fixture
def mgr(gpu_file):
    return GPUManager(gpu_file)


NVIDIA_SMI_OUTPUT = """\
index, memory.total [MiB], memory.used [MiB], memory.free [MiB], utilization.gpu [%]
0, 24576 MiB, 2048 MiB, 22528 MiB, 10 %
1, 24576 MiB, 20000 MiB, 4576 MiB, 95 %
"""


def test_detect_local_gpus(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = NVIDIA_SMI_OUTPUT
        gpus = mgr.detect_local()
    assert len(gpus) == 2
    assert gpus[0]["device"] == 0
    assert gpus[0]["memory_free"] == 22528
    assert gpus[1]["memory_free"] == 4576


def test_detect_local_no_nvidia_smi(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        gpus = mgr.detect_local()
    assert gpus == []


def test_allocate_picks_most_free(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = NVIDIA_SMI_OUTPUT
        result = mgr.allocate()
    assert result is not None
    host, device = result
    assert host == "local"
    assert device == 0  # GPU 0 has more free memory


def test_allocate_writes_status(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = NVIDIA_SMI_OUTPUT
        mgr.allocate(tag="exp-001")
    data = json.loads(gpu_file.read_text())
    allocated = [g for g in data["gpus"] if g["allocated_to"] == "exp-001"]
    assert len(allocated) == 1


def test_release(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = NVIDIA_SMI_OUTPUT
        mgr.allocate(tag="exp-001")
        mgr.release("local", 0)
    data = json.loads(gpu_file.read_text())
    g = [g for g in data["gpus"] if g["device"] == 0][0]
    assert g["allocated_to"] is None


def test_status(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = NVIDIA_SMI_OUTPUT
        mgr.refresh()
    status = mgr.status()
    assert len(status) == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gpu_manager.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/open_researcher/gpu_manager.py
"""GPU manager — detect, allocate, and release GPUs (local + remote)."""

import json
import subprocess
from pathlib import Path


class GPUManager:
    """Manage GPU allocation across local and remote hosts."""

    def __init__(self, status_file: Path, remote_hosts: list[dict] | None = None):
        self.status_file = status_file
        self.remote_hosts = remote_hosts or []

    def _read(self) -> dict:
        if self.status_file.exists():
            try:
                return json.loads(self.status_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"gpus": []}

    def _write(self, data: dict) -> None:
        self.status_file.write_text(json.dumps(data, indent=2))

    def _parse_nvidia_smi(self, output: str, host: str = "local") -> list[dict]:
        gpus = []
        for line in output.strip().splitlines()[1:]:  # skip header
            parts = [p.strip().replace(" MiB", "").replace(" %", "") for p in line.split(",")]
            if len(parts) < 5:
                continue
            try:
                gpus.append({
                    "host": host,
                    "device": int(parts[0]),
                    "memory_total": int(parts[1]),
                    "memory_used": int(parts[2]),
                    "memory_free": int(parts[3]),
                    "utilization": int(parts[4]),
                    "allocated_to": None,
                })
            except (ValueError, IndexError):
                continue
        return gpus

    def detect_local(self) -> list[dict]:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu",
             "--format=csv"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return []
        return self._parse_nvidia_smi(result.stdout, host="local")

    def detect_remote(self, host: str, user: str) -> list[dict]:
        cmd = (
            "nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu "
            "--format=csv"
        )
        result = subprocess.run(
            ["ssh", f"{user}@{host}", cmd],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        return self._parse_nvidia_smi(result.stdout, host=host)

    def refresh(self) -> list[dict]:
        all_gpus = self.detect_local()
        for rh in self.remote_hosts:
            try:
                all_gpus.extend(self.detect_remote(rh["host"], rh["user"]))
            except (subprocess.TimeoutExpired, OSError):
                continue
        # Preserve existing allocations
        old = self._read()
        old_alloc = {(g["host"], g["device"]): g.get("allocated_to") for g in old["gpus"]}
        for g in all_gpus:
            key = (g["host"], g["device"])
            if key in old_alloc:
                g["allocated_to"] = old_alloc[key]
        data = {"gpus": all_gpus}
        self._write(data)
        return all_gpus

    def allocate(self, tag: str | None = None) -> tuple[str, int] | None:
        gpus = self.refresh()
        free_gpus = [g for g in gpus if g["allocated_to"] is None]
        if not free_gpus:
            return None
        best = max(free_gpus, key=lambda g: g["memory_free"])
        best["allocated_to"] = tag
        self._write({"gpus": gpus})
        return (best["host"], best["device"])

    def release(self, host: str, device: int) -> None:
        data = self._read()
        for g in data["gpus"]:
            if g["host"] == host and g["device"] == device:
                g["allocated_to"] = None
        self._write(data)

    def status(self) -> list[dict]:
        return self._read()["gpus"]
```

**Step 4: Run tests**

Run: `pytest tests/test_gpu_manager.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/gpu_manager.py tests/test_gpu_manager.py
git commit -m "feat: add GPUManager for local+remote GPU allocation"
```

---

## Task 5: Create Idea Agent and Experiment Agent templates

**Files:**
- Create: `src/open_researcher/templates/idea_program.md.j2`
- Create: `src/open_researcher/templates/experiment_program.md.j2`

**Step 1: Create Idea Agent template**

```markdown
{# src/open_researcher/templates/idea_program.md.j2 #}
# Idea Agent — Research Idea Generator & Analyzer

You are the **Idea Agent** in a dual-agent research system. Your job is to maintain a pool of research ideas and analyze experiment results.

## Your Files

- **Read/Write**: `.research/idea_pool.json` — the shared idea pool
- **Read**: `.research/results.tsv` — experiment results (written by Experiment Agent)
- **Write**: `.research/activity.json` — update `idea_agent` key with your current status
- **Read**: `.research/literature.md`, `.research/project-understanding.md`

## Status Updates

Before each action, update your status in `.research/activity.json`:
```json
{"idea_agent": {"status": "<phase>", "detail": "<what you're doing>", "updated_at": "<ISO timestamp>"}}
```

Valid statuses: `analyzing`, `generating`, `searching`, `idle`

## Phase 1: Understand the Project

1. Read the codebase: source files, tests, documentation
2. Fill `.research/project-understanding.md` with your analysis
3. Update status: `{"status": "analyzing", "detail": "reading codebase"}`

## Phase 2: Research Related Work

1. If web search is available (`config.yaml: research.web_search: true`):
   - Search 3-5 technical queries related to the project
   - Read the most relevant results
2. Fill `.research/literature.md`
3. Update status: `{"status": "searching", "detail": "searching related work"}`

## Phase 3: Generate Initial Ideas

1. Based on project understanding and literature, generate 5-10 initial ideas
2. Write each idea to `.research/idea_pool.json` using this format:
```json
{"ideas": [{"id": "idea-001", "description": "...", "source": "literature|original", "category": "...", "priority": 1, "status": "pending", "assigned_experiment": null, "result": null, "created_at": "..."}]}
```
3. Prioritize by (expected impact) x (inverse complexity)
4. Categories: architecture, training, data, regularization, infrastructure
5. Update status: `{"status": "generating", "detail": "creating initial idea pool"}`

## Phase 4: Analysis Loop (Continuous)

Repeat forever:
1. Check `.research/results.tsv` for new experiment results
2. When a new result appears:
   a. Analyze: what worked, what didn't, why?
   b. Update status: `{"status": "analyzing", "detail": "reviewing experiment #N"}`
   c. Generate 1-3 new ideas based on the result
   d. Adjust priorities of existing pending ideas
   e. Update status: `{"status": "generating", "detail": "adding ideas from #N analysis"}`
3. Every {{ search_interval }} experiments: search for new techniques and add ideas
4. Sleep/wait 30 seconds before checking again

## Rules

- **Never** modify code or run experiments — that is the Experiment Agent's job
- **Always** update `activity.json` before each action
- **Always** use file locking when writing `idea_pool.json` (read, modify, write atomically)
- Check `.research/control.json` — if `paused: true`, wait until unpaused
- Keep idea descriptions specific and actionable (not "try something better")
- Tag source: `literature` for paper-inspired, `original` for your own, `user` for manually added
```

**Step 2: Create Experiment Agent template**

```markdown
{# src/open_researcher/templates/experiment_program.md.j2 #}
# Experiment Agent — Code Implementation & Evaluation

You are the **Experiment Agent** in a dual-agent research system. Your job is to pick ideas from the pool, implement them, run experiments, and record results.

## Your Files

- **Read/Write**: `.research/idea_pool.json` — pick ideas and update their status
- **Write**: `.research/results.tsv` — record experiment results via `.research/scripts/record.py`
- **Write**: `.research/activity.json` — update `experiment_agent` key with your current status
- **Read**: `.research/config.yaml` — experiment settings
- **Read**: `.research/evaluation.md` — how to evaluate
- **Read**: `.research/control.json` — pause/skip signals from user

## Status Updates

Before each action, update your status in `.research/activity.json`:
```json
{"experiment_agent": {"status": "<phase>", "idea": "<current idea>", "experiment": <N>, "gpu": {"host": "...", "device": 0}, "branch": "...", "started_at": "...", "updated_at": "..."}}
```

Valid statuses: `thinking`, `coding`, `evaluating`, `recording`, `idle`, `paused`

## Phase 1: Wait for Ideas

1. Poll `.research/idea_pool.json` until there are `pending` ideas
2. Update status: `{"status": "idle", "detail": "waiting for ideas"}`

## Phase 2: Design Evaluation (First Run Only)

If `.research/evaluation.md` is empty:
1. Design evaluation metrics and method
2. Fill `.research/evaluation.md`
3. Update `config.yaml` with `metrics.primary.name` and `direction`

## Phase 3: Establish Baseline (First Run Only)

If `.research/results.tsv` has no data rows:
1. Create branch: `git checkout -b research/{{ tag }}`
2. Run the evaluation command as defined in `evaluation.md`
3. Record baseline: `python .research/scripts/record.py --metric <name> --value <val> --status keep --desc "baseline"`
4. Git commit

## Phase 4: Experiment Loop (Continuous)

Repeat:
1. **Check control**: Read `.research/control.json`
   - If `paused: true`: set status to `paused`, wait 5s, recheck
   - If `skip_current: true`: mark current idea `skipped`, reset `skip_current` to false
2. **Pick idea**: Read `idea_pool.json`, select highest-priority `pending` idea
   - Mark it `running` with your experiment number
   - Update status: `{"status": "thinking", "idea": "<desc>"}`
3. **Implement**: Make code changes for the idea
   - Update status: `{"status": "coding", "idea": "<desc>"}`
   - Git commit the changes
4. **Evaluate**: Run the evaluation command
   - Update status: `{"status": "evaluating", "idea": "<desc>"}`
   - Timeout: `config.yaml: experiment.timeout` seconds (default 600)
5. **Record**: Parse results, call `record.py`
   - Update status: `{"status": "recording"}`
   - Compare to baseline:
     - Better → `status=keep`, keep the commit
     - Worse → `status=discard`, run `.research/scripts/rollback.sh`
     - Crash → `status=crash`, rollback, retry up to 2 times
6. **Update pool**: Mark idea as `done` with result in `idea_pool.json`
7. **Continue**: Go back to step 1

## GPU Selection

- Read `gpu_status.json` if it exists for allocated GPU
- Set `CUDA_VISIBLE_DEVICES=<device>` before running evaluation
- If the allocated GPU is on a remote host, run evaluation via SSH

## Crash Handling

- If evaluation crashes: retry up to 2 times
- After `max_consecutive_crashes` crashes in a row (default 3): pause and update status
- Always rollback failed experiments with `rollback.sh`

## Rules

- **Always** update `activity.json` before each action
- **Always** use file locking when writing `idea_pool.json`
- **Always** commit code changes before running evaluation
- **Never** generate or analyze ideas — that is the Idea Agent's job
- Check `control.json` at the start of every loop iteration
```

**Step 3: Verify templates render**

Run: `python -c "from jinja2 import Environment, PackageLoader; env = Environment(loader=PackageLoader('open_researcher', 'templates')); t1 = env.get_template('idea_program.md.j2'); t2 = env.get_template('experiment_program.md.j2'); print('OK:', len(t1.render(search_interval=5)), len(t2.render(tag='mar09')))"`
Expected: `OK: <number> <number>` — both render without error

**Step 4: Commit**

```bash
git add src/open_researcher/templates/idea_program.md.j2 src/open_researcher/templates/experiment_program.md.j2
git commit -m "feat: add Idea Agent and Experiment Agent instruction templates"
```

---

## Task 6: Update `init_cmd.py` — create new shared files on init

**Files:**
- Modify: `src/open_researcher/init_cmd.py`
- Modify: `tests/test_init.py`

**Step 1: Update test to verify new files**

Add to `tests/test_init.py`:

```python
def test_init_creates_shared_files(tmp_path):
    """Verify init creates idea_pool.json, activity.json, control.json."""
    do_init(repo_path=tmp_path, tag="test")
    research = tmp_path / ".research"

    pool = research / "idea_pool.json"
    assert pool.exists()
    data = json.loads(pool.read_text())
    assert data == {"ideas": []}

    activity = research / "activity.json"
    assert activity.exists()
    data = json.loads(activity.read_text())
    assert data == {}

    control = research / "control.json"
    assert control.exists()
    data = json.loads(control.read_text())
    assert data == {"paused": False, "skip_current": False}
```

Add `import json` at top of test file.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_init.py::test_init_creates_shared_files -v`
Expected: FAIL — `idea_pool.json` not found

**Step 3: Modify init_cmd.py**

After the `results.tsv` creation (line 46), add:

```python
    # Create shared coordination files for multi-agent mode
    (research_dir / "idea_pool.json").write_text(json.dumps({"ideas": []}, indent=2))
    (research_dir / "activity.json").write_text("{}")
    (research_dir / "control.json").write_text(json.dumps({"paused": False, "skip_current": False}, indent=2))
```

Add `import json` to the imports at top of `init_cmd.py`.

Also render the two new templates for multi-agent mode:

```python
    for template_name, output_name in [
        ("program.md.j2", "program.md"),
        ("config.yaml.j2", "config.yaml"),
        ("project-understanding.md.j2", "project-understanding.md"),
        ("evaluation.md.j2", "evaluation.md"),
        ("literature.md.j2", "literature.md"),
        ("ideas.md.j2", "ideas.md"),
        ("idea_program.md.j2", "idea_program.md"),
        ("experiment_program.md.j2", "experiment_program.md"),
    ]:
```

Update the context dict to include template variables:

```python
    config = yaml.safe_load(env.get_template("config.yaml.j2").render(context))
    search_interval = config.get("research", {}).get("search_interval", 5)
    context["search_interval"] = search_interval
```

Add `import yaml` to imports.

**Step 4: Run tests**

Run: `pytest tests/test_init.py -v`
Expected: All tests PASS (including new one)

**Step 5: Commit**

```bash
git add src/open_researcher/init_cmd.py tests/test_init.py
git commit -m "feat: init creates shared files for multi-agent coordination"
```

---

## Task 7: Update `config.yaml.j2` — add GPU config section

**Files:**
- Modify: `src/open_researcher/templates/config.yaml.j2`

**Step 1: Add GPU section to config template**

Append to `config.yaml.j2` after the `research:` block:

```yaml

# GPU configuration (for multi-agent mode)
gpu:
  # Remote hosts for GPU allocation (optional)
  # remote_hosts:
  #   - host: "192.168.1.100"
  #     user: "researcher"
  #   - host: "192.168.1.101"
  #     user: "researcher"
  remote_hosts: []
```

**Step 2: Verify template renders**

Run: `python -c "from jinja2 import Environment, PackageLoader; env = Environment(loader=PackageLoader('open_researcher', 'templates')); print(env.get_template('config.yaml.j2').render(tag='test'))"`
Expected: Template renders with GPU section

**Step 3: Commit**

```bash
git add src/open_researcher/templates/config.yaml.j2
git commit -m "feat: add GPU config section to config template"
```

---

## Task 8: Create Textual TUI — `tui/` package with app, widgets, modals, styles

**Files:**
- Create: `src/open_researcher/tui/__init__.py`
- Create: `src/open_researcher/tui/app.py`
- Create: `src/open_researcher/tui/widgets.py`
- Create: `src/open_researcher/tui/modals.py`
- Create: `src/open_researcher/tui/styles.css`
- Create: `tests/test_tui.py`

This is the largest task. It will be split into sub-steps.

**Step 1: Create `tui/__init__.py`**

```python
# src/open_researcher/tui/__init__.py
"""Textual TUI for Open Researcher."""
```

**Step 2: Create `tui/styles.css`**

```css
/* src/open_researcher/tui/styles.css */

Screen {
    background: $surface;
}

#stats-bar {
    dock: top;
    height: 1;
    background: $primary-background;
    color: $text;
    padding: 0 1;
}

#idea-pool {
    height: 1fr;
    border: solid $primary;
    padding: 0 1;
}

#idea-pool .idea-pending {
    color: $text;
}

#idea-pool .idea-running {
    color: $warning;
    text-style: bold;
}

#idea-pool .idea-done-kept {
    color: $success;
}

#idea-pool .idea-done-discarded {
    color: $error;
}

#idea-pool .idea-skipped {
    color: $text-muted;
}

#agent-panels {
    height: 1fr;
    layout: horizontal;
}

#idea-agent-panel {
    width: 1fr;
    border: solid $secondary;
    padding: 0 1;
}

#experiment-agent-panel {
    width: 2fr;
    border: solid $success;
    padding: 0 1;
}

#hotkey-bar {
    dock: bottom;
    height: 1;
    background: $primary-background;
    color: $text-muted;
    padding: 0 1;
}

AddIdeaModal {
    align: center middle;
}

AddIdeaModal > #dialog {
    width: 60;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

GPUStatusModal {
    align: center middle;
}

GPUStatusModal > #gpu-dialog {
    width: 80;
    height: auto;
    max-height: 80%;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

LogScreen {
    background: $surface;
}

LogScreen #log-content {
    height: 1fr;
    overflow-y: scroll;
    padding: 0 1;
}

LogScreen #log-footer {
    dock: bottom;
    height: 1;
    background: $primary-background;
    padding: 0 1;
}
```

**Step 3: Create `tui/widgets.py`**

```python
# src/open_researcher/tui/widgets.py
"""Custom Textual widgets for Open Researcher TUI."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatsBar(Static):
    """Top status bar showing experiment summary."""

    stats = reactive("")

    def render(self) -> str:
        return self.stats or "Open Researcher — starting..."

    def update_stats(self, state: dict) -> None:
        total = state.get("total", 0)
        keep = state.get("keep", 0)
        discard = state.get("discard", 0)
        crash = state.get("crash", 0)
        best = state.get("best_value")
        pm = state.get("primary_metric", "")

        parts = ["Open Researcher"]
        if total > 0:
            parts.append(f"{total} exp")
            parts.append(f"{keep} kept {discard} disc {crash} crash")
            if best is not None:
                parts.append(f"best {pm}={best:.4f}")
        else:
            parts.append("waiting for experiments...")

        self.stats = " | ".join(parts)


class IdeaPoolPanel(Widget):
    """Scrollable panel showing all ideas in the pool."""

    ideas_text = reactive("")

    def render(self) -> str:
        return self.ideas_text or "No ideas yet — Idea Agent is starting..."

    def update_ideas(self, ideas: list[dict], summary: dict) -> None:
        pending = summary.get("pending", 0)
        total = summary.get("total", 0)
        lines = [f"Idea Pool ({pending} pending / {total} total)"]
        lines.append("-" * 60)

        # Sort: running first, then pending by priority, then done/skipped
        status_order = {"running": 0, "pending": 1, "done": 2, "skipped": 3}
        sorted_ideas = sorted(ideas, key=lambda i: (status_order.get(i["status"], 9), i.get("priority", 99)))

        for idea in sorted_ideas:
            sid = idea["status"]
            desc = idea["description"][:45]
            iid = idea["id"].replace("idea-", "#")

            if sid == "running":
                exp = idea.get("assigned_experiment", "")
                lines.append(f">> {iid} {desc:<45} [RUNNING exp#{exp}]")
            elif sid == "pending":
                pri = idea.get("priority", "?")
                lines.append(f"   {iid} {desc:<45} [pending]  pri:{pri}")
            elif sid == "done":
                result = idea.get("result", {})
                verdict = result.get("verdict", "?")
                val = result.get("metric_value", 0)
                marker = "--" if verdict == "kept" else "xx"
                lines.append(f"{marker} {iid} {desc:<45} [{verdict} {val:.4f}]")
            elif sid == "skipped":
                lines.append(f"~~ {iid} {desc:<45} [skipped]")

        self.ideas_text = "\n".join(lines)


class AgentPanel(Widget):
    """Panel showing a single agent's status and recent output."""

    agent_text = reactive("")

    def render(self) -> str:
        return self.agent_text or "[idle]"

    def update_from_activity(self, activity: dict | None, agent_name: str, log_lines: list[str] | None = None) -> None:
        lines = [f"{agent_name}"]
        lines.append("-" * 30)

        if activity:
            status = activity.get("status", "idle")
            lines.append(f"[{status}]")

            detail = activity.get("detail", "")
            if detail:
                lines.append(detail)

            idea = activity.get("idea", "")
            if idea:
                lines.append(f"Idea: {idea}")

            gpu = activity.get("gpu")
            if gpu:
                lines.append(f"GPU: {gpu.get('host', '?')}:{gpu.get('device', '?')}")

            branch = activity.get("branch", "")
            if branch:
                lines.append(f"Branch: {branch}")

            started = activity.get("started_at", "")
            if started:
                lines.append(f"Started: {started[:19]}")
        else:
            lines.append("[idle] waiting to start...")

        if log_lines:
            lines.append("")
            for line in log_lines[-5:]:
                lines.append(f"> {line[:70]}")

        self.agent_text = "\n".join(lines)


class HotkeyBar(Static):
    """Bottom bar showing available keyboard shortcuts."""

    def render(self) -> str:
        return "[p]ause [r]esume [s]kip [a]dd idea [e]dit [g]pu [l]og [q]uit"
```

**Step 4: Create `tui/modals.py`**

```python
# src/open_researcher/tui/modals.py
"""Modal screens for Open Researcher TUI."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, Select, Static, TextArea


class AddIdeaModal(ModalScreen[dict | None]):
    """Modal dialog for adding a new idea to the pool."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Add New Idea")
            yield Input(placeholder="Idea description...", id="idea-desc")
            yield Select(
                [(c, c) for c in ["general", "architecture", "training", "data", "regularization", "infrastructure"]],
                value="general",
                id="idea-category",
            )
            yield Input(placeholder="Priority (1=highest)", id="idea-priority", value="5")
            yield Button("Add", variant="primary", id="btn-add")
            yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add":
            desc = self.query_one("#idea-desc", Input).value.strip()
            if desc:
                cat = self.query_one("#idea-category", Select).value
                try:
                    pri = int(self.query_one("#idea-priority", Input).value)
                except ValueError:
                    pri = 5
                self.dismiss({"description": desc, "category": cat, "priority": pri})
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class GPUStatusModal(ModalScreen):
    """Modal showing GPU status across all hosts."""

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, gpus: list[dict]):
        super().__init__()
        self.gpus = gpus

    def compose(self) -> ComposeResult:
        with Vertical(id="gpu-dialog"):
            yield Label("GPU Status")
            lines = []
            if not self.gpus:
                lines.append("No GPUs detected")
            for g in self.gpus:
                host = g.get("host", "?")
                dev = g.get("device", "?")
                total = g.get("memory_total", 0)
                used = g.get("memory_used", 0)
                free = g.get("memory_free", 0)
                alloc = g.get("allocated_to", None)
                status = f"[{alloc}]" if alloc else "[free]"
                lines.append(f"{host}:{dev}  {used}/{total} MiB  free:{free} MiB  {status}")
            yield Static("\n".join(lines))
            yield Button("Close", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()


class LogScreen(Screen):
    """Full-screen log viewer."""

    BINDINGS = [("escape", "go_back", "Back"), ("q", "go_back", "Back")]

    def __init__(self, log_path: str):
        super().__init__()
        self.log_path = log_path

    def compose(self) -> ComposeResult:
        from pathlib import Path
        content = ""
        p = Path(self.log_path)
        if p.exists():
            lines = p.read_text().splitlines()
            content = "\n".join(lines[-200:])  # last 200 lines
        yield TextArea(content, read_only=True, id="log-content")
        yield Static("Press [Esc] or [q] to return", id="log-footer")

    def action_go_back(self) -> None:
        self.app.pop_screen()
```

**Step 5: Create `tui/app.py`**

```python
# src/open_researcher/tui/app.py
"""Main Textual application for Open Researcher."""

import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches

from open_researcher.activity import ActivityMonitor
from open_researcher.idea_pool import IdeaPool
from open_researcher.status_cmd import parse_research_state
from open_researcher.tui.modals import AddIdeaModal, GPUStatusModal, LogScreen
from open_researcher.tui.widgets import AgentPanel, HotkeyBar, IdeaPoolPanel, StatsBar


class ResearchApp(App):
    """Interactive TUI for monitoring and controlling Open Researcher agents."""

    CSS_PATH = "styles.css"

    BINDINGS = [
        ("p", "pause", "Pause"),
        ("r", "resume", "Resume"),
        ("s", "skip", "Skip idea"),
        ("a", "add_idea", "Add idea"),
        ("g", "gpu_status", "GPU status"),
        ("l", "view_log", "View log"),
        ("q", "quit_app", "Quit"),
    ]

    def __init__(self, repo_path: Path, multi: bool = False):
        super().__init__()
        self.repo_path = repo_path
        self.research_dir = repo_path / ".research"
        self.multi = multi
        self.pool = IdeaPool(self.research_dir / "idea_pool.json")
        self.activity = ActivityMonitor(self.research_dir)
        self.idea_log_lines: list[str] = []
        self.exp_log_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield StatsBar(id="stats-bar")
        yield IdeaPoolPanel(id="idea-pool")
        with Horizontal(id="agent-panels"):
            yield AgentPanel(id="idea-agent-panel")
            yield AgentPanel(id="experiment-agent-panel")
        yield HotkeyBar(id="hotkey-bar")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._refresh_data)

    def _refresh_data(self) -> None:
        """Poll shared files and update all widgets."""
        # Stats
        try:
            state = parse_research_state(self.repo_path)
            self.query_one("#stats-bar", StatsBar).update_stats(state)
        except Exception:
            pass

        # Idea pool
        try:
            ideas = self.pool.all_ideas()
            summary = self.pool.summary()
            self.query_one("#idea-pool", IdeaPoolPanel).update_ideas(ideas, summary)
        except Exception:
            pass

        # Agent activity
        try:
            idea_act = self.activity.get("idea_agent")
            self.query_one("#idea-agent-panel", AgentPanel).update_from_activity(
                idea_act, "Idea Agent", self.idea_log_lines
            )
        except (NoMatches, Exception):
            pass

        try:
            exp_act = self.activity.get("experiment_agent")
            self.query_one("#experiment-agent-panel", AgentPanel).update_from_activity(
                exp_act, "Experiment Agent", self.exp_log_lines
            )
        except (NoMatches, Exception):
            pass

    def _read_control(self) -> dict:
        ctrl_path = self.research_dir / "control.json"
        if ctrl_path.exists():
            try:
                return json.loads(ctrl_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"paused": False, "skip_current": False}

    def _write_control(self, data: dict) -> None:
        ctrl_path = self.research_dir / "control.json"
        ctrl_path.write_text(json.dumps(data, indent=2))

    def action_pause(self) -> None:
        ctrl = self._read_control()
        ctrl["paused"] = True
        self._write_control(ctrl)
        self.notify("Experiment Agent paused")

    def action_resume(self) -> None:
        ctrl = self._read_control()
        ctrl["paused"] = False
        self._write_control(ctrl)
        self.notify("Experiment Agent resumed")

    def action_skip(self) -> None:
        ctrl = self._read_control()
        ctrl["skip_current"] = True
        self._write_control(ctrl)
        self.notify("Skipping current idea")

    def action_add_idea(self) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                self.pool.add(
                    result["description"],
                    source="user",
                    category=result["category"],
                    priority=result["priority"],
                )
                self.notify(f"Added idea: {result['description'][:40]}")

        self.push_screen(AddIdeaModal(), on_result)

    def action_gpu_status(self) -> None:
        gpu_path = self.research_dir / "gpu_status.json"
        gpus = []
        if gpu_path.exists():
            try:
                gpus = json.loads(gpu_path.read_text()).get("gpus", [])
            except (json.JSONDecodeError, OSError):
                pass
        self.push_screen(GPUStatusModal(gpus))

    def action_view_log(self) -> None:
        log_path = str(self.research_dir / "run.log")
        self.push_screen(LogScreen(log_path))

    def action_quit_app(self) -> None:
        self.exit()

    def append_idea_log(self, line: str) -> None:
        self.idea_log_lines.append(line)
        if len(self.idea_log_lines) > 100:
            self.idea_log_lines = self.idea_log_lines[-50:]

    def append_exp_log(self, line: str) -> None:
        self.exp_log_lines.append(line)
        if len(self.exp_log_lines) > 100:
            self.exp_log_lines = self.exp_log_lines[-50:]
```

**Step 6: Write basic TUI test**

```python
# tests/test_tui.py
"""Tests for Textual TUI components."""

import json
from pathlib import Path

import pytest

from open_researcher.tui.widgets import StatsBar, IdeaPoolPanel, AgentPanel


def test_stats_bar_update():
    bar = StatsBar()
    state = {"total": 7, "keep": 3, "discard": 2, "crash": 1, "best_value": 1.47, "primary_metric": "val_loss"}
    bar.update_stats(state)
    assert "7 exp" in bar.stats
    assert "3 kept" in bar.stats
    assert "1.47" in bar.stats


def test_stats_bar_empty():
    bar = StatsBar()
    bar.update_stats({"total": 0})
    assert "waiting" in bar.stats


def test_idea_pool_update():
    panel = IdeaPoolPanel()
    ideas = [
        {"id": "idea-001", "description": "cosine LR", "status": "running", "priority": 1, "assigned_experiment": 8, "result": None},
        {"id": "idea-002", "description": "gradient clip", "status": "pending", "priority": 2, "result": None},
    ]
    summary = {"pending": 1, "running": 1, "done": 0, "skipped": 0, "total": 2}
    panel.update_ideas(ideas, summary)
    assert "cosine LR" in panel.ideas_text
    assert "RUNNING" in panel.ideas_text
    assert "pending" in panel.ideas_text


def test_agent_panel_update():
    panel = AgentPanel()
    activity = {"status": "evaluating", "idea": "cosine LR", "gpu": {"host": "local", "device": 0}, "branch": "exp/cosine-lr"}
    panel.update_from_activity(activity, "Experiment Agent", ["Epoch 4/10 loss=1.43"])
    assert "evaluating" in panel.agent_text
    assert "cosine LR" in panel.agent_text
    assert "Epoch 4" in panel.agent_text


def test_agent_panel_no_activity():
    panel = AgentPanel()
    panel.update_from_activity(None, "Idea Agent")
    assert "idle" in panel.agent_text
```

**Step 7: Run tests**

Run: `pytest tests/test_tui.py -v`
Expected: All 5 tests PASS

**Step 8: Commit**

```bash
git add src/open_researcher/tui/ tests/test_tui.py
git commit -m "feat: add Textual TUI app with widgets, modals, and styles"
```

---

## Task 9: Rewrite `run_cmd.py` — dual-agent orchestration + Textual TUI launch

**Files:**
- Modify: `src/open_researcher/run_cmd.py`
- Modify: `tests/test_run.py`

**Step 1: Update test file**

Add multi-agent tests to `tests/test_run.py`:

```python
def test_run_multi_fails_without_research_dir(tmp_path, monkeypatch):
    """Multi-agent mode requires .research/ directory."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        from open_researcher.run_cmd import do_run_multi
        do_run_multi(repo_path=tmp_path, idea_agent_name=None, exp_agent_name=None, dry_run=False)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_run.py::test_run_multi_fails_without_research_dir -v`
Expected: FAIL — `cannot import name 'do_run_multi'`

**Step 3: Rewrite `run_cmd.py`**

```python
# src/open_researcher/run_cmd.py
"""Run command — launch AI agents with interactive Textual TUI."""

import signal
import subprocess
import threading
from pathlib import Path

from rich.console import Console

from open_researcher.agents import detect_agent, get_agent

console = Console()


def _launch_agent_thread(
    agent,
    workdir: Path,
    program_md: Path,
    on_output,
    done_event: threading.Event,
    exit_codes: dict,
    key: str,
):
    """Run an agent in a background thread."""
    def _run():
        try:
            code = agent.run(workdir, on_output=on_output)
        except Exception:
            code = 1
        exit_codes[key] = code
        done_event.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def do_run(repo_path: Path, agent_name: str | None, dry_run: bool) -> None:
    """Single-agent mode — backward compatible."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    program_md = research / "program.md"
    if not program_md.exists():
        console.print("[red]Error:[/red] .research/program.md not found.")
        raise SystemExit(1)

    agent = _resolve_agent(agent_name)

    if dry_run:
        cmd = agent.build_command(program_md, repo_path)
        console.print(f"[bold]Agent:[/bold] {agent.name}")
        console.print(f"[bold]Command:[/bold] {' '.join(cmd[:3])}...")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run -- no agent launched.[/dim]")
        return

    # Launch with Textual TUI
    from open_researcher.tui.app import ResearchApp

    app = ResearchApp(repo_path, multi=False)
    done = threading.Event()
    exit_codes = {}

    def on_output(line: str):
        app.append_exp_log(line)
        log_path = research / "run.log"
        with open(log_path, "a") as f:
            f.write(line + "\n")

    _launch_agent_thread(agent, repo_path, program_md, on_output, done, exit_codes, "agent")
    app.run()

    code = exit_codes.get("agent", 0)
    if code == 0:
        console.print(f"\n[green]Agent {agent.name} completed successfully.[/green]")
    else:
        console.print(f"\n[red]Agent {agent.name} exited with code {code}.[/red]")

    from open_researcher.status_cmd import print_status
    print_status(repo_path)


def do_run_multi(
    repo_path: Path,
    idea_agent_name: str | None,
    exp_agent_name: str | None,
    dry_run: bool,
) -> None:
    """Dual-agent mode — Idea Agent + Experiment Agent in parallel."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    idea_program = research / "idea_program.md"
    exp_program = research / "experiment_program.md"

    for p in [idea_program, exp_program]:
        if not p.exists():
            console.print(f"[red]Error:[/red] {p.name} not found. Re-run 'open-researcher init'.")
            raise SystemExit(1)

    idea_agent = _resolve_agent(idea_agent_name)
    exp_agent = _resolve_agent(exp_agent_name)

    if dry_run:
        console.print(f"[bold]Idea Agent:[/bold] {idea_agent.name}")
        console.print(f"[bold]Experiment Agent:[/bold] {exp_agent.name}")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run -- no agents launched.[/dim]")
        return

    # Launch with Textual TUI
    from open_researcher.tui.app import ResearchApp

    app = ResearchApp(repo_path, multi=True)
    done_idea = threading.Event()
    done_exp = threading.Event()
    exit_codes = {}

    def on_idea_output(line: str):
        app.append_idea_log(line)
        log_path = research / "idea_agent.log"
        with open(log_path, "a") as f:
            f.write(line + "\n")

    def on_exp_output(line: str):
        app.append_exp_log(line)
        log_path = research / "experiment_agent.log"
        with open(log_path, "a") as f:
            f.write(line + "\n")

    _launch_agent_thread(idea_agent, repo_path, idea_program, on_idea_output, done_idea, exit_codes, "idea")
    _launch_agent_thread(exp_agent, repo_path, exp_program, on_exp_output, done_exp, exit_codes, "exp")

    app.run()

    for key, name in [("idea", "Idea Agent"), ("exp", "Experiment Agent")]:
        code = exit_codes.get(key, 0)
        if code == 0:
            console.print(f"[green]{name} completed successfully.[/green]")
        else:
            console.print(f"[red]{name} exited with code {code}.[/red]")

    from open_researcher.status_cmd import print_status
    print_status(repo_path)


def _resolve_agent(agent_name: str | None):
    """Resolve agent by name or auto-detect."""
    if agent_name:
        try:
            return get_agent(agent_name)
        except KeyError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise SystemExit(1)
    agent = detect_agent()
    if agent is None:
        console.print(
            "[red]Error:[/red] No supported AI agent found.\n"
            "Install one of: claude (Claude Code), codex, aider, opencode\n"
            "Or specify with: --agent <name>"
        )
        raise SystemExit(1)
    console.print(f"[green]Auto-detected agent:[/green] {agent.name}")
    return agent
```

**Step 4: Run tests**

Run: `pytest tests/test_run.py -v`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add src/open_researcher/run_cmd.py tests/test_run.py
git commit -m "feat: rewrite run_cmd with dual-agent orchestration + Textual TUI"
```

---

## Task 10: Update `cli.py` — add multi-agent params, remove dashboard command

**Files:**
- Modify: `src/open_researcher/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Rewrite cli.py**

```python
# src/open_researcher/cli.py
"""Open Researcher CLI — research workflow framework for AI agents."""

from pathlib import Path

import typer

app = typer.Typer(
    name="open-researcher",
    help="Research workflow framework for AI agents. "
         "Initialize automated experiment tracking in any repo.",
)


@app.command()
def init(tag: str = typer.Option(None, help="Experiment tag (e.g. mar8). Defaults to today's date.")):
    """Initialize .research/ directory in the current repo."""
    from open_researcher.init_cmd import do_init
    do_init(repo_path=Path.cwd(), tag=tag)


@app.command()
def status():
    """Show current research progress."""
    from open_researcher.status_cmd import print_status
    print_status(Path.cwd())


@app.command()
def results():
    """Print experiment results table."""
    from open_researcher.results_cmd import print_results
    print_results(Path.cwd())


@app.command()
def export():
    """Export experiment report as Markdown."""
    from open_researcher.export_cmd import do_export
    do_export(Path.cwd())


@app.command()
def run(
    agent: str = typer.Option(None, help="Agent to use (claude-code, codex, aider, opencode)."),
    multi: bool = typer.Option(False, "--multi", help="Enable dual-agent mode (Idea + Experiment)."),
    idea_agent: str = typer.Option(None, "--idea-agent", help="Agent for idea generation (multi mode)."),
    exp_agent: str = typer.Option(None, "--exp-agent", help="Agent for experiments (multi mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the command without executing."),
):
    """Launch AI agent(s) to run the research workflow."""
    if multi or idea_agent or exp_agent:
        from open_researcher.run_cmd import do_run_multi
        do_run_multi(
            repo_path=Path.cwd(),
            idea_agent_name=idea_agent or agent,
            exp_agent_name=exp_agent or agent,
            dry_run=dry_run,
        )
    else:
        from open_researcher.run_cmd import do_run
        do_run(repo_path=Path.cwd(), agent_name=agent, dry_run=dry_run)


if __name__ == "__main__":
    app()
```

**Step 2: Update CLI test — remove dashboard test**

In `tests/test_cli.py`, remove or update any test referencing the `dashboard` command.

**Step 3: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/open_researcher/cli.py tests/test_cli.py
git commit -m "feat: add --multi/--idea-agent/--exp-agent CLI params, remove dashboard"
```

---

## Task 11: Remove dashboard code

**Files:**
- Delete: `src/open_researcher/dashboard/app.py`
- Delete: `src/open_researcher/dashboard/templates/index.html`
- Delete: `src/open_researcher/dashboard/__init__.py` (if exists)
- Delete: `tests/test_dashboard.py`

**Step 1: Remove files**

```bash
rm -rf src/open_researcher/dashboard/
rm -f tests/test_dashboard.py
```

**Step 2: Run all tests to ensure nothing breaks**

Run: `pytest -v`
Expected: All remaining tests PASS, no import errors

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove web dashboard (replaced by Textual TUI)"
```

---

## Task 12: Update `status_cmd.py` — show agent activity in status output

**Files:**
- Modify: `src/open_researcher/status_cmd.py`
- Modify: `tests/test_status.py`

**Step 1: Add activity display to `print_status()`**

After the existing status panel output in `print_status()`, add:

```python
    # Show agent activity if available
    activity_path = research / "activity.json"
    if activity_path.exists():
        from open_researcher.activity import ActivityMonitor
        monitor = ActivityMonitor(research)
        all_act = monitor.get_all()
        if all_act:
            act_lines = ["", "  Agent Activity:"]
            for key, act in all_act.items():
                status = act.get("status", "idle")
                detail = act.get("detail", "")
                act_lines.append(f"    {key}: [{status}] {detail}")
            console.print(Panel("\n".join(act_lines), title="Agents", border_style="green"))
```

**Step 2: Add test**

```python
def test_print_status_shows_activity(tmp_path):
    """Status should show agent activity when activity.json exists."""
    research = tmp_path / ".research"
    research.mkdir()
    # ... setup config, results, etc.
    (research / "activity.json").write_text(json.dumps({
        "idea_agent": {"status": "analyzing", "detail": "reviewing #3"}
    }))
    # verify no crash
    from open_researcher.status_cmd import parse_research_state
    state = parse_research_state(tmp_path)
    assert state is not None
```

**Step 3: Run tests**

Run: `pytest tests/test_status.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/open_researcher/status_cmd.py tests/test_status.py
git commit -m "feat: show agent activity in status command"
```

---

## Task 13: Integration test — full multi-agent workflow

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Add multi-agent integration test**

```python
def test_multi_agent_init_creates_all_files(tmp_path):
    """Verify init creates all files needed for multi-agent mode."""
    from open_researcher.init_cmd import do_init
    do_init(repo_path=tmp_path, tag="test")
    research = tmp_path / ".research"

    # Original files
    assert (research / "program.md").exists()
    assert (research / "config.yaml").exists()
    assert (research / "results.tsv").exists()

    # Multi-agent files
    assert (research / "idea_pool.json").exists()
    assert (research / "activity.json").exists()
    assert (research / "control.json").exists()
    assert (research / "idea_program.md").exists()
    assert (research / "experiment_program.md").exists()

    # Verify idea_pool.json structure
    import json
    pool = json.loads((research / "idea_pool.json").read_text())
    assert pool == {"ideas": []}

    # Verify control.json structure
    ctrl = json.loads((research / "control.json").read_text())
    assert ctrl["paused"] is False
    assert ctrl["skip_current"] is False


def test_idea_pool_workflow(tmp_path):
    """Test the full idea lifecycle: add → pick → run → done."""
    from open_researcher.idea_pool import IdeaPool
    pool_file = tmp_path / "idea_pool.json"
    pool_file.write_text('{"ideas": []}')
    pool = IdeaPool(pool_file)

    # Add ideas
    pool.add("cosine LR", source="literature", category="training", priority=1)
    pool.add("dropout 0.3", source="original", category="regularization", priority=2)

    # Pick highest priority
    pending = pool.list_by_status("pending")
    assert pending[0]["description"] == "cosine LR"

    # Mark running
    pool.update_status(pending[0]["id"], "running", experiment=1)
    assert pool.summary()["running"] == 1

    # Mark done
    pool.mark_done(pending[0]["id"], metric_value=0.87, verdict="kept")
    assert pool.summary()["done"] == 1
    assert pool.summary()["pending"] == 1
```

**Step 2: Run tests**

Run: `pytest tests/test_integration.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add multi-agent integration tests"
```

---

## Task 14: Run full test suite and lint

**Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests PASS

**Step 2: Run linter**

Run: `ruff check src/ tests/`
Expected: No errors (fix any issues found)

**Step 3: Run formatter**

Run: `ruff format --check src/ tests/`
Expected: No formatting issues (fix any found)

**Step 4: Final commit if any fixes**

```bash
git add -A
git commit -m "fix: resolve lint and formatting issues"
```

---

## Summary of all tasks

| Task | Description | New Files | Modified Files |
|------|-------------|-----------|----------------|
| 1 | Update dependencies | — | `pyproject.toml` |
| 2 | IdeaPool file manager | `idea_pool.py`, `test_idea_pool.py` | — |
| 3 | ActivityMonitor | `activity.py`, `test_activity.py` | — |
| 4 | GPUManager | `gpu_manager.py`, `test_gpu_manager.py` | — |
| 5 | Agent templates | `idea_program.md.j2`, `experiment_program.md.j2` | — |
| 6 | Update init_cmd | — | `init_cmd.py`, `test_init.py` |
| 7 | Update config template | — | `config.yaml.j2` |
| 8 | Textual TUI package | `tui/` (5 files), `test_tui.py` | — |
| 9 | Rewrite run_cmd | — | `run_cmd.py`, `test_run.py` |
| 10 | Update CLI | — | `cli.py`, `test_cli.py` |
| 11 | Remove dashboard | — | Delete `dashboard/`, `test_dashboard.py` |
| 12 | Update status_cmd | — | `status_cmd.py`, `test_status.py` |
| 13 | Integration tests | — | `test_integration.py` |
| 14 | Final lint + test | — | — |
