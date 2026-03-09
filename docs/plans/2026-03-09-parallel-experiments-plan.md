# Parallel Experiments Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 支持多 idea 并发跑在不同 GPU 上 + 单 idea 多卡 DDP，同时修复 TUI 显示问题。

**Architecture:** Master Experiment Agent 做调度决策，spawn sub-agent worker 到独立 git worktree 执行。每个 worker 绑定特定 GPU。TUI 用 RichLog 实现实时日志流。

**Tech Stack:** Python 3.10+, Textual (RichLog), Git Worktree, subprocess, fcntl file locking

---

### Task 1: IdeaPool 增加 gpu_hint 字段和 claim_idea 原子操作

**Files:**
- Modify: `src/open_researcher/idea_pool.py:35-50`
- Test: `tests/test_idea_pool.py`

**Step 1: 写失败测试**

在 `tests/test_idea_pool.py` 末尾添加：

```python
def test_add_idea_with_gpu_hint(pool, pool_file):
    pool.add("DDP training experiment", priority=1, gpu_hint=4)
    data = json.loads(pool_file.read_text())
    assert data["ideas"][0]["gpu_hint"] == 4


def test_add_idea_default_gpu_hint(pool, pool_file):
    pool.add("simple experiment", priority=1)
    data = json.loads(pool_file.read_text())
    assert data["ideas"][0]["gpu_hint"] == "auto"


def test_claim_idea_atomic(pool):
    pool.add("idea A", priority=1)
    pool.add("idea B", priority=2)
    claimed = pool.claim_idea(worker_id="w-001")
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["claimed_by"] == "w-001"
    # Second claim should get a different idea
    claimed2 = pool.claim_idea(worker_id="w-002")
    assert claimed2 is not None
    assert claimed2["id"] != claimed["id"]


def test_claim_idea_none_available(pool):
    result = pool.claim_idea(worker_id="w-001")
    assert result is None
```

**Step 2: 跑测试确认失败**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_idea_pool.py -v`
Expected: FAIL — `gpu_hint` 参数不存在, `claim_idea` 方法不存在

**Step 3: 实现**

修改 `src/open_researcher/idea_pool.py`:

`add()` 方法签名改为：
```python
def add(self, description: str, source: str = "original", category: str = "general",
        priority: int = 5, gpu_hint: int | str = "auto") -> dict:
```

idea dict 中增加：
```python
"gpu_hint": gpu_hint,
"claimed_by": None,
```

新增 `claim_idea()` 方法：
```python
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
```

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_idea_pool.py -v`
Expected: ALL PASS

**Step 5: 提交**

```bash
git add src/open_researcher/idea_pool.py tests/test_idea_pool.py
git commit -m "feat: add gpu_hint field and claim_idea atomic operation to IdeaPool"
```

---

### Task 2: GPUManager 增加 allocate_group 方法

**Files:**
- Modify: `src/open_researcher/gpu_manager.py:86-94`
- Test: `tests/test_gpu_manager.py`

**Step 1: 写失败测试**

在 `tests/test_gpu_manager.py` 末尾添加：

```python
NVIDIA_SMI_4GPU = """\
index, memory.total [MiB], memory.used [MiB], memory.free [MiB], utilization.gpu [%]
0, 24576 MiB, 2048 MiB, 22528 MiB, 10 %
1, 24576 MiB, 3000 MiB, 21576 MiB, 15 %
2, 24576 MiB, 20000 MiB, 4576 MiB, 95 %
3, 24576 MiB, 1000 MiB, 23576 MiB, 5 %
"""


def test_allocate_group(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_4GPU)
        result = mgr.allocate_group(count=2, tag="exp-multi")
    assert result is not None
    assert len(result) == 2
    # Should pick the 2 GPUs with most free memory (device 3 and 0)
    devices = [r[1] for r in result]
    assert 3 in devices
    assert 0 in devices


def test_allocate_group_not_enough(mgr):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        result = mgr.allocate_group(count=5, tag="exp-big")
    assert result is None


def test_allocate_group_single(mgr):
    """allocate_group(1) should behave like allocate()."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_OUTPUT)
        result = mgr.allocate_group(count=1, tag="exp-single")
    assert result is not None
    assert len(result) == 1


def test_release_group(mgr, gpu_file):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=NVIDIA_SMI_4GPU)
        gpus = mgr.allocate_group(count=2, tag="exp-multi")
        mgr.release_group(gpus)
    data = json.loads(gpu_file.read_text())
    for g in data["gpus"]:
        assert g["allocated_to"] is None
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_gpu_manager.py -v`
Expected: FAIL — `allocate_group` 和 `release_group` 不存在

**Step 3: 实现**

在 `src/open_researcher/gpu_manager.py` 添加：

```python
def allocate_group(self, count: int = 1, tag: str | None = None) -> list[tuple[str, int]] | None:
    """Allocate a group of N GPUs sorted by most free memory. Returns None if not enough."""
    gpus = self.refresh()
    free_gpus = [g for g in gpus if g["allocated_to"] is None]
    if len(free_gpus) < count:
        return None
    free_gpus.sort(key=lambda g: g["memory_free"], reverse=True)
    selected = free_gpus[:count]
    for g in selected:
        g["allocated_to"] = tag
    self._write({"gpus": gpus})
    return [(g["host"], g["device"]) for g in selected]

def release_group(self, gpu_list: list[tuple[str, int]]) -> None:
    """Release a group of GPUs."""
    for host, device in gpu_list:
        self.release(host, device)
```

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_gpu_manager.py -v`
Expected: ALL PASS

**Step 5: 提交**

```bash
git add src/open_researcher/gpu_manager.py tests/test_gpu_manager.py
git commit -m "feat: add allocate_group and release_group to GPUManager"
```

---

### Task 3: ActivityMonitor 支持 workers 数组

**Files:**
- Modify: `src/open_researcher/activity.py`
- Test: `tests/test_activity.py`

**Step 1: 写失败测试**

在 `tests/test_activity.py` 末尾添加：

```python
def test_update_worker(tmp_path):
    from open_researcher.activity import ActivityMonitor
    am = ActivityMonitor(tmp_path)
    am.update_worker("experiment_master", "w-001", status="coding", idea="idea-001", gpus=[0])
    data = am.get("experiment_master")
    assert "workers" in data
    assert len(data["workers"]) == 1
    assert data["workers"][0]["id"] == "w-001"
    assert data["workers"][0]["status"] == "coding"


def test_update_worker_multiple(tmp_path):
    from open_researcher.activity import ActivityMonitor
    am = ActivityMonitor(tmp_path)
    am.update_worker("experiment_master", "w-001", status="coding", idea="idea-001", gpus=[0])
    am.update_worker("experiment_master", "w-002", status="evaluating", idea="idea-002", gpus=[1, 2])
    data = am.get("experiment_master")
    assert len(data["workers"]) == 2


def test_remove_worker(tmp_path):
    from open_researcher.activity import ActivityMonitor
    am = ActivityMonitor(tmp_path)
    am.update_worker("experiment_master", "w-001", status="coding", idea="idea-001", gpus=[0])
    am.remove_worker("experiment_master", "w-001")
    data = am.get("experiment_master")
    assert len(data["workers"]) == 0
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_activity.py -v`
Expected: FAIL — `update_worker` 和 `remove_worker` 不存在

**Step 3: 实现**

在 `src/open_researcher/activity.py` 添加：

```python
def update_worker(self, agent_key: str, worker_id: str, **kwargs) -> None:
    """Update or add a worker entry within an agent's activity."""
    data = self._read()
    entry = data.get(agent_key, {})
    workers = entry.get("workers", [])
    found = False
    for w in workers:
        if w["id"] == worker_id:
            w.update(kwargs)
            w["updated_at"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    if not found:
        worker = {"id": worker_id, **kwargs, "updated_at": datetime.now(timezone.utc).isoformat()}
        workers.append(worker)
    entry["workers"] = workers
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    data[agent_key] = entry
    self._write(data)

def remove_worker(self, agent_key: str, worker_id: str) -> None:
    """Remove a worker entry."""
    data = self._read()
    entry = data.get(agent_key, {})
    workers = entry.get("workers", [])
    entry["workers"] = [w for w in workers if w["id"] != worker_id]
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    data[agent_key] = entry
    self._write(data)
```

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_activity.py -v`
Expected: ALL PASS

**Step 5: 提交**

```bash
git add src/open_researcher/activity.py tests/test_activity.py
git commit -m "feat: add worker tracking to ActivityMonitor"
```

---

### Task 4: 创建 worker_prompt.md.j2 模板

**Files:**
- Create: `src/open_researcher/templates/worker_prompt.md.j2`
- Test: `tests/test_init.py` (验证模板可渲染)

**Step 1: 写失败测试**

在 `tests/test_init.py` 中添加：

```python
def test_worker_prompt_template_renders():
    from jinja2 import Environment, PackageLoader
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("worker_prompt.md.j2")
    result = tmpl.render(
        idea_id="idea-003",
        idea_description="Use cosine annealing with warmup",
        gpu_devices="0,1",
        gpu_count=2,
        worktree_path="/tmp/worktree-003",
        evaluation_content="# Eval\nRun train.py",
        config_content="mode: autonomous",
        tag="demo",
    )
    assert "idea-003" in result
    assert "cosine annealing" in result
    assert "CUDA_VISIBLE_DEVICES=0,1" in result
    assert "torchrun" in result  # multi-GPU hint
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_init.py::test_worker_prompt_template_renders -v`
Expected: FAIL — template not found

**Step 3: 创建模板**

创建 `src/open_researcher/templates/worker_prompt.md.j2`:

```markdown
# Experiment Worker — {{ idea_id }}

You are an **Experiment Worker** executing a single idea. Complete the task and exit.

## Your Idea

**ID:** {{ idea_id }}
**Description:** {{ idea_description }}

## GPU Assignment

- **Devices:** {{ gpu_devices }}
- **GPU Count:** {{ gpu_count }}
- **Environment variable:** `CUDA_VISIBLE_DEVICES={{ gpu_devices }}`

{% if gpu_count > 1 %}
**IMPORTANT:** You have {{ gpu_count }} GPUs. Use distributed training:
- PyTorch: `torchrun --nproc_per_node={{ gpu_count }} train.py ...`
- Or set `CUDA_VISIBLE_DEVICES={{ gpu_devices }}` and use DataParallel
{% endif %}

## Working Directory

Your workspace is: `{{ worktree_path }}`
All file operations happen here. Do NOT modify any files outside this directory.

## Configuration

```yaml
{{ config_content }}
```

## Evaluation Method

{{ evaluation_content }}

## Steps

1. **Implement the idea**: Make code changes to implement "{{ idea_description }}"
2. **Commit**: `git add -A && git commit -m "exp: {{ idea_id }} - {{ idea_description[:50] }}"`
3. **Set GPU**: `export CUDA_VISIBLE_DEVICES={{ gpu_devices }}`
4. **Run evaluation**: Follow the evaluation method above
5. **Report result**: Print the primary metric value as: `RESULT: <metric_name>=<value>`
6. **Exit**: Your job is done after reporting the result

## Rules

- Do NOT modify `.research/idea_pool.json` — the Master Agent handles that
- Do NOT modify files outside your worktree
- Always set `CUDA_VISIBLE_DEVICES={{ gpu_devices }}` before running any training/evaluation
- If evaluation crashes, print `RESULT: CRASH` and exit
- Keep implementation focused and minimal
```

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_init.py::test_worker_prompt_template_renders -v`
Expected: PASS

**Step 5: 提交**

```bash
git add src/open_researcher/templates/worker_prompt.md.j2 tests/test_init.py
git commit -m "feat: add worker_prompt.md.j2 template for sub-agent workers"
```

---

### Task 5: 重写 experiment_program.md.j2 为 Master 模式

**Files:**
- Modify: `src/open_researcher/templates/experiment_program.md.j2`
- Test: `tests/test_init.py` (验证模板渲染)

**Step 1: 写失败测试**

```python
def test_experiment_program_master_mode():
    from jinja2 import Environment, PackageLoader
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("experiment_program.md.j2")
    result = tmpl.render(tag="demo")
    assert "Master" in result or "master" in result
    assert "sub-agent" in result or "worker" in result
    assert "git worktree" in result
    assert "CUDA_VISIBLE_DEVICES" in result
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_init.py::test_experiment_program_master_mode -v`
Expected: FAIL — current template doesn't mention Master/worktree

**Step 3: 重写模板**

替换 `src/open_researcher/templates/experiment_program.md.j2` 全部内容为：

```markdown
# Experiment Master Agent — Parallel Experiment Orchestrator

You are the **Experiment Master Agent**. You orchestrate parallel experiments by spawning sub-agent workers across GPUs.

## Your Files

- **Read/Write**: `.research/idea_pool.json` — claim ideas, update results
- **Read/Write**: `.research/activity.json` — track worker status under `experiment_master` key
- **Write**: `.research/results.tsv` — record results via `.research/scripts/record.py`
- **Read**: `.research/config.yaml` — experiment settings
- **Read**: `.research/evaluation.md` — evaluation method
- **Read**: `.research/control.json` — pause/skip signals
- **Read**: `.research/gpu_status.json` — GPU availability

## Phase 1: Detect GPUs

1. Run `nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu --format=csv`
2. Parse available GPUs and their free memory
3. Write GPU info to `.research/gpu_status.json`
4. If no GPUs detected, you will run experiments serially on CPU

## Phase 2: Establish Baseline (First Run Only)

If `.research/results.tsv` has no data rows:
1. Run the evaluation command from `evaluation.md` directly (no worktree needed)
2. Record baseline: `python .research/scripts/record.py --metric <name> --value <val> --status keep --desc "baseline"`
3. Git commit

## Phase 3: Scheduling Loop (Continuous)

Repeat:

### 3a. Check Control
- Read `.research/control.json`
- If `paused: true`: wait 10s, recheck
- If `skip_current: true`: skip, reset flag

### 3b. Assess Resources
- Refresh GPU status
- Count: available GPUs, currently running workers, pending ideas
- Read `idea_pool.json` for pending ideas (sorted by priority)

### 3c. Decide Allocation
For each pending idea, decide how many GPUs to assign:
- **Many ideas, few GPUs**: 1 GPU per idea, maximize parallelism
- **Few ideas, many GPUs**: Give high-priority ideas more GPUs for faster training
- **Idea has `gpu_hint` field**: Respect the hint (`1`, `2`, `4`, `"all"`, or `"auto"`)
- **`gpu_hint: "auto"`**: You decide based on the idea's nature (e.g., "DDP training" → multi-GPU)

### 3d. Spawn Workers
For each (idea, gpu_list) pair:

1. **Claim idea**: Update idea status to `running` in `idea_pool.json`
2. **Create worktree**:
   ```bash
   git worktree add .research/worktrees/w-{idea_id} -b exp/{idea_id}
   ```
3. **Copy shared files**: Copy `.research/evaluation.md` and `.research/config.yaml` to the worktree's `.research/`
4. **Generate worker prompt**: Create `.research/worktrees/w-{idea_id}/worker_prompt.md` with:
   - The idea description
   - GPU assignment (CUDA_VISIBLE_DEVICES)
   - Evaluation method
   - Instructions to implement, evaluate, and report result
5. **Launch sub-agent**:
   ```bash
   cd .research/worktrees/w-{idea_id}
   CUDA_VISIBLE_DEVICES={devices} claude -p "$(cat worker_prompt.md)" --allowedTools Edit,Write,Bash,Read,Glob,Grep
   ```
   Run this in the background (use `&` or a subshell)
6. **Update activity**: Add worker to `.research/activity.json` under `experiment_master.workers`

### 3e. Monitor Workers
- Check if any spawned worker processes have completed
- For each completed worker:
  1. Parse output for `RESULT: <metric>=<value>` or `RESULT: CRASH`
  2. If good result (better than baseline):
     - Merge: `cd <repo_root> && git merge exp/{idea_id}`
     - Record: `python .research/scripts/record.py --metric <m> --value <v> --status keep --desc "{idea_desc}"`
  3. If bad result or crash:
     - Record: `python .research/scripts/record.py --metric <m> --value <v> --status discard --desc "{idea_desc}"`
     - Rollback: `.research/scripts/rollback.sh`
  4. Cleanup:
     - `git worktree remove .research/worktrees/w-{idea_id}`
     - `git branch -d exp/{idea_id}` (if merged) or `git branch -D exp/{idea_id}` (if discarded)
     - Release GPUs
     - Update idea in `idea_pool.json` to `done` with result
     - Remove worker from `activity.json`

### 3f. Wait and Loop
- Sleep 10 seconds
- Go back to 3a

## Status Updates

Keep `.research/activity.json` updated:
```json
{
  "experiment_master": {
    "status": "scheduling",
    "workers": [
      {"id": "w-001", "idea": "idea-001", "gpus": [0], "status": "evaluating"},
      {"id": "w-002", "idea": "idea-002", "gpus": [1, 2], "status": "coding"}
    ],
    "gpu_total": 4,
    "gpu_active": 3,
    "updated_at": "..."
  }
}
```

## CPU-Only Fallback

If no GPUs detected:
- Run experiments serially (one at a time, no worktree needed)
- Fall back to the simple sequential experiment loop
- Still use `idea_pool.json` for idea management

## Rules

- **Always** check `control.json` at the start of every loop
- **Always** update `activity.json` with current worker status
- **Always** clean up worktrees after experiments complete
- **Never** run more workers than available GPUs
- **Never** generate ideas — that is the Idea Agent's job
- Sub-agents should exit after one experiment — do not let them loop
```

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_init.py::test_experiment_program_master_mode -v`
Expected: PASS

**Step 5: 提交**

```bash
git add src/open_researcher/templates/experiment_program.md.j2 tests/test_init.py
git commit -m "feat: rewrite experiment_program.md.j2 as Master orchestrator"
```

---

### Task 6: TUI — 用 RichLog 替换 AgentPanel

**Files:**
- Modify: `src/open_researcher/tui/widgets.py:76-119`
- Modify: `src/open_researcher/tui/app.py`
- Modify: `src/open_researcher/tui/styles.css`
- Test: `tests/test_tui.py`

**Step 1: 写失败测试**

替换 `tests/test_tui.py` 中的 agent panel 测试：

```python
def test_worker_status_panel_update():
    from open_researcher.tui.widgets import WorkerStatusPanel
    panel = WorkerStatusPanel()
    workers = [
        {"id": "w-001", "idea": "idea-001", "gpus": [0], "status": "evaluating"},
        {"id": "w-002", "idea": "idea-002", "gpus": [1, 2], "status": "coding"},
    ]
    panel.update_workers(workers, gpu_total=4)
    text = panel.workers_text
    assert "w-001" in text
    assert "GPU:0" in text
    assert "evaluating" in text
    assert "GPU:1,2" in text


def test_worker_status_panel_empty():
    from open_researcher.tui.widgets import WorkerStatusPanel
    panel = WorkerStatusPanel()
    panel.update_workers([], gpu_total=0)
    assert "No workers" in panel.workers_text or "idle" in panel.workers_text


def test_idea_pool_shows_gpu_info():
    from open_researcher.tui.widgets import IdeaPoolPanel
    panel = IdeaPoolPanel()
    ideas = [
        {
            "id": "idea-001", "description": "cosine LR", "status": "running",
            "priority": 1, "assigned_experiment": 8, "result": None,
            "gpu_hint": 2, "claimed_by": "w-001",
        },
    ]
    summary = {"pending": 0, "running": 1, "done": 0, "skipped": 0, "total": 1}
    panel.update_ideas(ideas, summary)
    assert "cosine LR" in panel.ideas_text
    assert "RUNNING" in panel.ideas_text
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_tui.py -v`
Expected: FAIL — `WorkerStatusPanel` 不存在

**Step 3: 实现 widgets.py 改动**

修改 `src/open_researcher/tui/widgets.py`:

保留 `StatsBar` 和 `HotkeyBar` 不变。

修改 `IdeaPoolPanel.update_ideas()` 支持显示 GPU 信息（`claimed_by` 字段）。

新增 `WorkerStatusPanel`：

```python
class WorkerStatusPanel(Widget):
    """Panel showing experiment workers and their GPU assignments."""

    workers_text = reactive("")

    def render(self) -> str:
        return self.workers_text or "Experiment Master — idle"

    def update_workers(self, workers: list[dict], gpu_total: int = 0) -> None:
        if not workers:
            active = 0
        else:
            active = sum(len(w.get("gpus", [])) for w in workers)
        lines = [f"Experiment Master | Workers: {len(workers)} | GPU: {active}/{gpu_total} active"]
        lines.append("-" * 60)
        if not workers:
            lines.append("No workers running — waiting for ideas...")
        for w in workers:
            wid = w.get("id", "?")
            idea = w.get("idea", "?")
            gpus = w.get("gpus", [])
            gpu_str = ",".join(str(g) for g in gpus)
            status = w.get("status", "?")
            lines.append(f"  {wid}: {idea} [GPU:{gpu_str}] [{status}]")
        self.workers_text = "\n".join(lines)
```

保留 `AgentPanel` 供 Idea Agent 使用，但简化为只渲染日志（后续 app.py 会用 RichLog 替代）。

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_tui.py -v`
Expected: ALL PASS

**Step 5: 提交**

```bash
git add src/open_researcher/tui/widgets.py tests/test_tui.py
git commit -m "feat: add WorkerStatusPanel, update IdeaPoolPanel for GPU info"
```

---

### Task 7: TUI App — RichLog + thread-safe output + 多 worker 显示

**Files:**
- Modify: `src/open_researcher/tui/app.py`
- Modify: `src/open_researcher/tui/styles.css`

**Step 1: 重写 app.py compose()**

关键改动：
1. Idea Agent 面板用 `RichLog` 替代 `AgentPanel` — 支持实时滚动
2. Experiment 区域分为 `WorkerStatusPanel`（上）+ `RichLog`（下）
3. `append_idea_log` 和 `append_exp_log` 用 `call_from_thread` 保证线程安全
4. `_refresh_data` 读取 `activity.json` 中的 `experiment_master.workers` 更新 `WorkerStatusPanel`

```python
from textual.widgets import RichLog

def compose(self) -> ComposeResult:
    yield StatsBar(id="stats-bar")
    yield IdeaPoolPanel(id="idea-pool")
    with Horizontal(id="agent-panels"):
        with Vertical(id="idea-agent-section"):
            yield Static("Idea Agent", classes="panel-title")
            yield RichLog(id="idea-log", wrap=True, markup=True)
        with Vertical(id="exp-agent-section"):
            yield WorkerStatusPanel(id="worker-status")
            yield RichLog(id="exp-log", wrap=True, markup=True)
    yield HotkeyBar(id="hotkey-bar")

def append_idea_log(self, line: str) -> None:
    self.call_from_thread(self._do_append_idea_log, line)

def _do_append_idea_log(self, line: str) -> None:
    try:
        self.query_one("#idea-log", RichLog).write(line)
    except Exception:
        pass

def append_exp_log(self, line: str) -> None:
    self.call_from_thread(self._do_append_exp_log, line)

def _do_append_exp_log(self, line: str) -> None:
    try:
        self.query_one("#exp-log", RichLog).write(line)
    except Exception:
        pass
```

**Step 2: 更新 styles.css**

```css
#idea-agent-section {
    width: 1fr;
    height: 1fr;
}

#exp-agent-section {
    width: 2fr;
    height: 1fr;
}

.panel-title {
    height: 1;
    background: $primary-background;
    padding: 0 1;
}

#worker-status {
    height: auto;
    max-height: 8;
    border-bottom: solid $accent;
    padding: 0 1;
}

#idea-log, #exp-log {
    height: 1fr;
    border: solid $primary;
}
```

**Step 3: 更新 _refresh_data**

```python
def _refresh_data(self) -> None:
    # ... existing stats/idea pool refresh ...

    # Refresh worker status from activity.json
    try:
        exp_master = self.activity.get("experiment_master")
        if exp_master:
            workers = exp_master.get("workers", [])
            gpu_total = exp_master.get("gpu_total", 0)
            self.query_one("#worker-status", WorkerStatusPanel).update_workers(workers, gpu_total)
    except Exception:
        pass
```

**Step 4: 手动验证**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -c "from open_researcher.tui.app import ResearchApp; print('import ok')"`
Expected: `import ok`

**Step 5: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

**Step 6: 提交**

```bash
git add src/open_researcher/tui/app.py src/open_researcher/tui/styles.css
git commit -m "feat: rewrite TUI with RichLog streaming and WorkerStatusPanel"
```

---

### Task 8: run_cmd.py — 适配 Master Agent 模式

**Files:**
- Modify: `src/open_researcher/run_cmd.py`
- Test: `tests/test_run.py`

**Step 1: 写失败测试**

```python
def test_run_multi_dry_run_shows_master(capsys):
    from open_researcher.run_cmd import do_run_multi
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        research = repo / ".research"
        research.mkdir()
        (research / "idea_program.md").write_text("Idea instructions")
        (research / "experiment_program.md").write_text("Master instructions")
        mock_idea = MagicMock()
        mock_idea.name = "claude-code"
        mock_exp = MagicMock()
        mock_exp.name = "claude-code"

        with patch("open_researcher.run_cmd.get_agent", side_effect=[mock_idea, mock_exp]):
            do_run_multi(repo, idea_agent_name="claude-code", exp_agent_name="claude-code", dry_run=True)

        captured = capsys.readouterr()
        assert "Idea Agent" in captured.out
        assert "Experiment" in captured.out
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_run.py::test_run_multi_dry_run_shows_master -v`
Expected: FAIL — dry run 输出格式不匹配

**Step 3: 修改 run_cmd.py**

修改 `do_run_multi()` 的 dry_run 输出：

```python
if dry_run:
    console.print(f"[bold]Idea Agent:[/bold] {idea_agent.name}")
    console.print(f"[bold]Experiment Master Agent:[/bold] {exp_agent.name}")
    console.print(f"[bold]Working directory:[/bold] {repo_path}")
    console.print("\n[dim]Dry run -- no agents launched.[/dim]")
    return
```

确保 `on_exp_output` 和 `on_idea_output` 使用 `app.append_*_log()` 的线程安全版本（Task 7 已处理）。

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_run.py -v`
Expected: ALL PASS

**Step 5: 提交**

```bash
git add src/open_researcher/run_cmd.py tests/test_run.py
git commit -m "feat: update run_cmd for Master Agent mode"
```

---

### Task 9: init_cmd.py — 初始化 gpu_status.json 和 worktrees 目录

**Files:**
- Modify: `src/open_researcher/init_cmd.py:58-61`
- Test: `tests/test_init.py`

**Step 1: 写失败测试**

```python
def test_init_creates_gpu_status_file(init_dir):
    """init should create gpu_status.json."""
    gpu_file = init_dir / "gpu_status.json"
    assert gpu_file.exists()
    data = json.loads(gpu_file.read_text())
    assert "gpus" in data


def test_init_creates_worktrees_dir(init_dir):
    """init should create .research/worktrees/ directory."""
    worktrees = init_dir / "worktrees"
    assert worktrees.is_dir()
```

**Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_init.py -v`
Expected: FAIL — gpu_status.json 和 worktrees/ 不存在

**Step 3: 实现**

在 `src/open_researcher/init_cmd.py` 的共享文件创建部分添加：

```python
# Create GPU status file
(research_dir / "gpu_status.json").write_text(json.dumps({"gpus": []}, indent=2))

# Create worktrees directory for parallel experiments
(research_dir / "worktrees").mkdir()
```

**Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_init.py -v`
Expected: ALL PASS

**Step 5: 提交**

```bash
git add src/open_researcher/init_cmd.py tests/test_init.py
git commit -m "feat: init creates gpu_status.json and worktrees directory"
```

---

### Task 10: 全量测试 + lint

**Files:**
- All modified files

**Step 1: 跑 ruff lint**

Run: `python -m ruff check src/ tests/ --fix`
Expected: 0 errors (或修复后 0 errors)

**Step 2: 跑 ruff format**

Run: `python -m ruff format src/ tests/`

**Step 3: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

**Step 4: 提交 lint 修复（如有）**

```bash
git add -u
git commit -m "chore: fix lint issues"
```

---

### Task 11: 更新 run_demo.sh 展示并发模式

**Files:**
- Modify: `run_demo.sh`

**Step 1: 在 run_demo.sh 的提示信息中添加并发模式说明**

在 Step 10 的输出部分添加：

```bash
echo "  ──── 并发实验模式 (多GPU) ────"
echo "  open-researcher run --multi --agent claude-code"
echo "  # Master Agent 自动检测 GPU 并分配 worker"
echo ""
```

**Step 2: 跑 shellcheck（如有）**

Run: `shellcheck run_demo.sh || true`

**Step 3: 提交**

```bash
git add run_demo.sh
git commit -m "docs: update demo script with parallel experiment mode"
```

---

## 总结

| Task | 内容 | 关键文件 |
|------|------|---------|
| 1 | IdeaPool: gpu_hint + claim_idea | idea_pool.py |
| 2 | GPUManager: allocate_group | gpu_manager.py |
| 3 | ActivityMonitor: workers 数组 | activity.py |
| 4 | worker_prompt.md.j2 模板 | templates/ |
| 5 | experiment_program.md.j2 Master 模式 | templates/ |
| 6 | TUI: WorkerStatusPanel | tui/widgets.py |
| 7 | TUI: RichLog + thread-safe | tui/app.py, styles.css |
| 8 | run_cmd: Master Agent 适配 | run_cmd.py |
| 9 | init_cmd: gpu_status + worktrees | init_cmd.py |
| 10 | 全量 lint + test | all |
| 11 | 更新 demo 脚本 | run_demo.sh |
