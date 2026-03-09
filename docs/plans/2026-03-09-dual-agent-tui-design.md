# Dual-Agent Architecture + Runtime TUI Design

## Goal

Replace the current single-agent loop with a two-agent parallel architecture (Idea Agent + Experiment Agent) and build a real-time TUI that shows what each agent is doing, the idea pool status, and experiment progress.

## Problem

The current TUI only shows experiment statistics and the last 15 lines of agent stdout. Users cannot tell:
- What phase/step the agent is in (thinking, coding, training, analyzing)
- Which idea is being tried
- Whether the agent is idle, thinking, or running a long evaluation
- How the idea pipeline looks (what's pending, running, done)

## Architecture

### Two-Agent System

```
                    ┌─────────────────┐
                    │   Orchestrator   │
                    │   (run_cmd.py)   │
                    └──────┬──────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    ┌─────────────────┐      ┌──────────────────┐
    │   Idea Agent     │      │ Experiment Agent  │
    │   (AI process)   │      │   (AI process)    │
    └────────┬────────┘      └────────┬─────────┘
             │                        │
             ▼                        ▼
    ┌────────────────── Shared Files ──────────────┐
    │  idea_pool.json  activity.json  results.tsv  │
    └──────────────────────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────┐
    │              TUI (Rich Live)                  │
    │  Stats | Idea Pool | Agent Status | Logs      │
    └──────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Responsibility | Trigger |
|-------|---------------|---------|
| **Idea Agent** | Analyze repo + results + literature → maintain idea pool | Init + after each experiment result |
| **Experiment Agent** | Pick idea → implement → select GPU/branch → run eval → record | Continuously when pending ideas exist |

### Coordination Protocol

1. Idea Agent writes ideas to `idea_pool.json` with status `pending`
2. Experiment Agent reads pool, picks highest priority `pending` → marks `running`
3. Experiment Agent completes → marks idea `done` with result, writes to `results.tsv`
4. Idea Agent watches `results.tsv` → analyzes new result → generates/adjusts ideas
5. Both agents update `activity.json` with their current status

## Data Formats

### idea_pool.json

```json
{
  "ideas": [
    {
      "id": "idea-001",
      "description": "cosine LR decay with warmup 500 steps",
      "source": "literature",
      "category": "lr_schedule",
      "priority": 1,
      "status": "pending|running|done",
      "assigned_experiment": null,
      "result": null,
      "created_at": "2026-03-09T15:00:00Z"
    }
  ]
}
```

Status flow: `pending` → `running` → `done`

When `done`, result is filled:
```json
"result": {"metric_value": 1.49, "verdict": "kept|discarded|crashed"}
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
    "status": "thinking|coding|evaluating|analyzing|recording|idle",
    "idea": "cosine LR + warmup",
    "experiment": 8,
    "started_at": "2026-03-09T15:30:00Z",
    "updated_at": "2026-03-09T15:32:34Z"
  }
}
```

## TUI Layout

```
┌─ Open Researcher ─────────────────────────────┐
│ 7 exp | 3 kept 2 disc 1 crash | best=1.47 -3% │
├─ Idea Pool (3 pending) ───────────────────────┤
│ >> cosine LR + warmup        [RUNNING #8]     │
│    gradient clipping 1.0     [pending]        │
│    AdamW + lr=3e-4           [pending]        │
│ -- dropout 0.2               [kept 1.49]      │
│ xx doubled n_head            [disc 1.55]      │
├─ Idea Agent ──────┬─ Experiment Agent ────────┤
│ [analyzing]       │ [eval 2m34s] GPU:0        │
│ reviewing #7      │ branch: exp/cosine-lr     │
│                   │ > Epoch 4/10 loss=1.43    │
└───────────────────┴───────────────────────────┘
```

Four regions:
1. **Stats row** — one-line summary
2. **Idea Pool** — all ideas visible (`>>` running, `--` kept, `xx` discarded, space = pending)
3. **Idea Agent status** — left bottom, what the idea agent is doing
4. **Experiment Agent status** — right bottom, current idea + eval progress + GPU + log tail

## New Template Files

### idea_program.md.j2

Idea Agent instructions:
- Phase 1: Analyze repository structure, understand codebase, read existing docs
- Phase 2: Search related papers/repos/blogs (if web-capable)
- Generate initial idea pool → write `idea_pool.json`
- **Loop**: Watch `results.tsv` for new entries → analyze result → generate new ideas → update priorities
- Update `activity.json["idea_agent"]` at each step

### experiment_program.md.j2

Experiment Agent instructions:
- Wait for `idea_pool.json` to contain `pending` ideas
- Pick highest priority pending idea → mark `running` in pool
- Implement code changes on experiment branch
- Git commit → run evaluation command → parse results
- Record via `record.py` → mark idea `done` in pool
- Update `activity.json["experiment_agent"]` at each step
- Loop to next idea

### Single-agent backward compatibility

Keep existing `program.md.j2` for `open-researcher run --agent X` (single-agent mode).
Dual-agent mode activated with `--multi` flag or `--idea-agent`/`--exp-agent` flags.

## ActivityMonitor Class

New file: `src/open_researcher/activity.py`

```python
class ActivityMonitor:
    def __init__(self, research_dir: Path):
        self.activity_file = research_dir / "activity.json"
        self.pool_file = research_dir / "idea_pool.json"

    def get_activity(self, agent_key: str) -> dict | None:
        """Read activity for a specific agent."""

    def get_idea_pool(self) -> list[dict]:
        """Read all ideas from pool."""

    def get_pool_summary(self) -> dict:
        """Count pending/running/done ideas."""

    def elapsed(self, agent_key: str) -> str:
        """Calculate elapsed time for current activity."""
```

## CLI Changes

```python
@app.command()
def run(
    agent: str = typer.Option(None, help="Agent for single-agent mode."),
    multi: bool = typer.Option(False, "--multi", help="Enable dual-agent mode."),
    idea_agent: str = typer.Option(None, help="Agent for idea generation."),
    exp_agent: str = typer.Option(None, help="Agent for experiments."),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
```

- `--multi`: use same agent for both roles
- `--idea-agent` / `--exp-agent`: different agents for each role
- Default (no flags): single-agent mode (backward compatible)

## Files to Modify

| File | Change |
|------|--------|
| Create: `src/open_researcher/activity.py` | ActivityMonitor class |
| Create: `src/open_researcher/templates/idea_program.md.j2` | Idea Agent instructions |
| Create: `src/open_researcher/templates/experiment_program.md.j2` | Experiment Agent instructions |
| Modify: `src/open_researcher/run_cmd.py` | Add `do_run_multi()`, new TUI layout, activity panel |
| Modify: `src/open_researcher/cli.py` | Add `--multi`, `--idea-agent`, `--exp-agent` params |
| Modify: `src/open_researcher/init_cmd.py` | Create empty `idea_pool.json` and `activity.json` |
| Modify: `src/open_researcher/status_cmd.py` | Read activity.json for agent status |
| Modify: `src/open_researcher/run_cmd.py` | Update single-agent TUI to also use activity.json |
| Create: `tests/test_activity.py` | ActivityMonitor tests |
| Modify: `tests/test_run.py` | Add multi-agent tests |
| Modify: `tests/test_init.py` | Verify new files created |

## Design Decisions

1. **File-based coordination** over IPC — simplest, agents already read/write files
2. **JSON over YAML** for idea_pool — faster parsing, atomic writes
3. **No emoji in TUI** — use ASCII markers (`>>`, `--`, `xx`) for terminal compatibility
4. **Per-agent activity keys** — `idea_agent` and `experiment_agent` as fixed keys
5. **Backward compatible** — single-agent mode preserved, dual-agent opt-in
