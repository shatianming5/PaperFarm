# Multi-Agent Architecture + Interactive TUI Redesign

## Goal

Replace the current single-agent + Rich Live TUI with:
1. Dual-agent parallel architecture (Idea Agent + Experiment Agent)
2. Textual-based interactive TUI with full keyboard control
3. GPU management (local + remote)
4. Remove web dashboard

## Architecture

```
                        ┌───────────────────────┐
                        │     Orchestrator       │
                        │  (run_cmd.py:do_run)   │
                        └──────────┬────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
          ┌──────────────────┐          ┌──────────────────┐
          │    Idea Agent     │          │ Experiment Agent  │
          │   (subprocess)    │          │   (subprocess)    │
          └────────┬─────────┘          └────────┬─────────┘
                   │                             │
                   ▼                             ▼
         ┌────────────────────── Shared Files ──────────────────┐
         │  idea_pool.json   activity.json   results.tsv       │
         │  control.json     gpu_status.json  config.yaml      │
         └─────────────────────────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────────────────────────────────────────┐
         │           Textual TUI (interactive terminal)         │
         │  poll files → update UI → accept input → write files │
         └─────────────────────────────────────────────────────┘
```

## Agent Roles

| Agent | Responsibility | Input | Output |
|-------|---------------|-------|--------|
| **Idea Agent** | Analyze repo + results + literature → maintain idea pool | repo code, `results.tsv`, `idea_pool.json` | `idea_pool.json` (add/modify), `activity.json` |
| **Experiment Agent** | Pick pending idea → implement → select GPU+branch → evaluate → record | `idea_pool.json`, `config.yaml` | `results.tsv`, git commits, `idea_pool.json` (status update), `activity.json` |

## Coordination Protocol

1. Idea Agent writes ideas to `idea_pool.json` with status `pending`
2. Experiment Agent polls pool, picks highest priority `pending` → marks `running`
3. Experiment Agent completes → marks `done`, fills result, writes `results.tsv`
4. Idea Agent watches `results.tsv` changes → analyzes → generates/adjusts ideas
5. File read/write protected by fcntl file locks

## Data Formats

### idea_pool.json

```json
{
  "ideas": [
    {
      "id": "idea-001",
      "description": "cosine LR decay with warmup 500 steps",
      "source": "literature|original|user",
      "category": "lr_schedule",
      "priority": 1,
      "status": "pending|running|done|skipped",
      "assigned_experiment": null,
      "result": null,
      "created_at": "2026-03-09T15:00:00Z"
    }
  ]
}
```

### activity.json

```json
{
  "idea_agent": {
    "status": "analyzing|generating|searching|idle",
    "detail": "reviewing experiment #7 result",
    "updated_at": "2026-03-09T15:32:00Z"
  },
  "experiment_agent": {
    "status": "thinking|coding|evaluating|recording|idle|paused",
    "idea": "cosine LR + warmup",
    "experiment": 8,
    "gpu": {"host": "local", "device": 0},
    "branch": "exp/cosine-lr",
    "started_at": "2026-03-09T15:30:00Z",
    "updated_at": "2026-03-09T15:32:34Z"
  }
}
```

### control.json (TUI → Agent control signals)

```json
{
  "paused": false,
  "skip_current": false
}
```

### gpu_status.json

```json
{
  "gpus": [
    {"host": "local", "device": 0, "memory_total": 24576, "memory_used": 2048, "allocated_to": null},
    {"host": "gpu-server", "device": 0, "memory_total": 81920, "memory_used": 0, "allocated_to": "exp-008"}
  ]
}
```

## TUI Layout (Textual)

```
╔══════════════════════════════════════════════════════════════╗
║  Open Researcher  7 exp │ 3 kept 2 disc 1 crash │ best=1.47║
╠══════════════════════════════════════════════════════════════╣
║  Idea Pool (3 pending / 5 total)                    [a]dd   ║
║  ─────────────────────────────────────────────────────────  ║
║  >> #8 cosine LR + warmup           [RUNNING]    pri:1     ║
║     #9 gradient clipping 1.0        [pending]    pri:2     ║
║     #10 AdamW + lr=3e-4             [pending]    pri:3     ║
║  ── #7 dropout 0.2                  [kept 1.49]            ║
║  xx #6 doubled n_head               [disc 1.55]            ║
╠═══════════════════════════╤══════════════════════════════════╣
║  Idea Agent               │  Experiment Agent               ║
║  ─────────────            │  ────────────────                ║
║  [analyzing]              │  [evaluating] 2m34s             ║
║  reviewing exp #7 result  │  GPU: gpu-server:0              ║
║  generating new ideas...  │  Branch: exp/cosine-lr          ║
║                           │  > Epoch 4/10 loss=1.43         ║
║                           │  > val_loss=1.48                ║
╠═══════════════════════════╧══════════════════════════════════╣
║  [p]ause [r]esume [s]kip [a]dd idea [e]dit [g]pu [l]og [q]uit║
╚══════════════════════════════════════════════════════════════╝
```

### Hotkeys

| Key | Action |
|-----|--------|
| `p` | Pause Experiment Agent |
| `r` | Resume Experiment Agent |
| `s` | Skip current idea (mark skipped) |
| `a` | Add idea modal (input description + category + priority) |
| `e` | Edit idea pool (select/reorder/delete ideas) |
| `g` | GPU status modal (all GPUs, local + remote) |
| `l` | Full-screen log viewer |
| `q` | Graceful quit (SIGTERM, wait for agent cleanup) |
| `Tab` | Switch focus between panels |

## GPU Management

- **Local**: Parse `nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv`
- **Remote**: `ssh host nvidia-smi ...` for each configured SSH host
- **Allocation**: Pick GPU with most free memory, set `CUDA_VISIBLE_DEVICES`
- **Tracking**: `gpu_status.json` records allocations
- **Config**: SSH hosts defined in `config.yaml` under `gpu.remote_hosts`

## Textual Components

```python
class ResearchApp(App):
    class StatsBar(Static)           # Top status bar
    class IdeaPoolPanel(Widget)      # Scrollable idea list
    class AgentPanel(Widget)         # Agent status + log tail
    class HotkeyBar(Static)          # Bottom hotkey hints

    # Modals
    class AddIdeaModal(ModalScreen)  # Add idea popup
    class GPUStatusModal(ModalScreen)# GPU status popup
    class LogViewer(Screen)          # Full-screen log
```

## Files to Create

| File | Purpose |
|------|---------|
| `src/open_researcher/activity.py` | ActivityMonitor class |
| `src/open_researcher/gpu_manager.py` | GPU detect/allocate/release |
| `src/open_researcher/idea_pool.py` | IdeaPool read/write with file locking |
| `src/open_researcher/tui/app.py` | Textual main application |
| `src/open_researcher/tui/widgets.py` | Custom widgets (StatsBar, IdeaPoolPanel, AgentPanel) |
| `src/open_researcher/tui/modals.py` | Modals (AddIdea, GPUStatus, LogViewer) |
| `src/open_researcher/tui/styles.css` | Textual CSS styles |
| `src/open_researcher/templates/idea_program.md.j2` | Idea Agent instructions |
| `src/open_researcher/templates/experiment_program.md.j2` | Experiment Agent instructions |

## Files to Modify

| File | Change |
|------|--------|
| `cli.py` | Add `--multi`/`--idea-agent`/`--exp-agent`/`--gpu-config` params; remove `dashboard` command |
| `run_cmd.py` | Add `do_run_multi()` dual-agent orchestration; replace Rich Live with Textual app launch |
| `init_cmd.py` | Create `idea_pool.json`, `activity.json`, `control.json` on init |
| `status_cmd.py` | Read `activity.json` for agent status display |
| `pyproject.toml` | Add `textual` dependency; remove `fastapi`/`uvicorn` |

## Files to Delete

| File | Reason |
|------|--------|
| `dashboard/app.py` | Web dashboard removed |
| `dashboard/templates/index.html` | Web dashboard removed |

## Error Handling

- Agent process crash: Orchestrator detects exit code, TUI shows error, optional restart
- File lock timeout: Retry 3x then error
- GPU unavailable: Fallback to CPU or wait for release
- SSH connection failure: Mark host unavailable, pick next

## Backward Compatibility

- `open-researcher run --agent X` (no `--multi`): Single-agent mode preserved, TUI upgraded to Textual (simplified single-agent layout)
- All existing `results.tsv`, `config.yaml` formats unchanged
