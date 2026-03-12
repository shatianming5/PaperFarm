> [English](repo_inventory.en.md) · [简体中文](repo_inventory.md)

## Tree
- `src/open_researcher/`: main source code
- `src/open_researcher/agents/`: agent adapters
- `src/open_researcher/tui/`: Textual TUI
- `src/open_researcher/scripts/`: runtime helper scripts
- `tests/`: pytest test suite
- `docs/`: documentation and plans
- `examples/`: target-repo examples
- `analysis/`: analysis notes
- `.research/`: runtime state directory

## Entry Points
- `pyproject.toml`: exposes `open-researcher` (primary) and `PaperFarm` (compat alias) CLI entrypoints
- `src/open_researcher/cli.py`: main CLI (`run/init/status/results/export/doctor/demo`)
- `src/open_researcher/run_cmd.py`: interactive bootstrap/TUI path
- `src/open_researcher/headless.py`: headless bootstrap/JSONL path
- `src/open_researcher/init_cmd.py`: `.research/` template/state initialization
- `src/open_researcher/config_cmd.py`: `open-researcher config show|validate`
- `src/open_researcher/ideas_cmd.py`: `open-researcher ideas list|add|delete|prioritize`
- `src/open_researcher/logs_cmd.py`: `open-researcher logs`

## Core Modules
- `src/open_researcher/workflow_options.py`: normalizes CLI options into interactive/headless + worker topology
- `src/open_researcher/agent_runtime.py`: agent auto-detection and explicit resolution
- `src/open_researcher/research_loop.py`: core `Scout -> Manager -> Critic -> Experiment` orchestration
- `src/open_researcher/research_events.py`: typed event contract mapped to `events.jsonl`
- `src/open_researcher/event_journal.py`: JSONL event write/read helpers
- `src/open_researcher/graph_protocol.py`: `research-v1` init and role-agent resolution
- `src/open_researcher/research_graph.py`: canonical hypothesis/evidence/frontier graph
- `src/open_researcher/research_memory.py`: repo prior / ideation / experiment memory
- `src/open_researcher/parallel_runtime.py`: parallel worker runtime
- `src/open_researcher/tui/app.py`: interactive monitoring UI
- `src/open_researcher/tui/events.py`: typed event to TUI log rendering
- `src/open_researcher/status_cmd.py`: `.research/` progress/status summary
- `src/open_researcher/results_cmd.py`: load/print/chart `results.tsv`

## Config & Runtime Data
- Config file: `.research/config.yaml`
- Key config fields:
  - `experiment.max_experiments`
  - `experiment.max_parallel_workers`
  - `metrics.primary.name`
  - `metrics.primary.direction`
  - `research.protocol = research-v1`
  - `research.manager_batch_size`
  - `research.critic_repro_policy`
  - `roles.scout_agent|manager_agent|critic_agent|experiment_agent`
  - `memory.ideation|experiment|repo_type_prior`
- Runtime files:
  - `.research/scout_program.md`
  - `.research/.internal/role_programs/manager.md`
  - `.research/.internal/role_programs/critic.md`
  - `.research/.internal/role_programs/experiment.md`
  - `.research/idea_pool.json`
  - `.research/results.tsv`
  - `.research/events.jsonl`
  - `.research/research_graph.json`
  - `.research/research_memory.json`
  - `.research/activity.json`
  - `.research/control.json`
  - `.research/gpu_status.json`
- External prerequisites:
  - must run inside a git repository
  - at least one supported agent CLI: `claude-code` / `codex` / `aider` / `opencode` / `kimi-cli` / `gemini-cli`
  - parallel workers assume local or remote GPU availability when enabled, but GPU is not globally required

## How To Run
```bash
open-researcher init
open-researcher run --agent codex
open-researcher run --mode headless --goal "improve latency"
open-researcher run --agent codex --workers 1
open-researcher run --agent codex --workers 4
open-researcher status
open-researcher results
open-researcher results --chart primary
open-researcher export
open-researcher config show
open-researcher ideas list
pytest -q
```

## Risks / Unknowns
- Current external interface is CLI + config + runtime files + typed events (not HTTP service).
- `research-v1` is the only execution protocol, but parallel worker flows still use `idea_pool.json` as a compatibility projection.
- Both TUI and headless consume the same typed event stream; graph tracing is fully visible under `research-v1`.
