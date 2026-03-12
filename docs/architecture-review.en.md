# Architecture Review (English Summary)

[English Summary](architecture-review.en.md) · [简体中文](architecture-review.md)

## Scope

This is an English summary of the full Chinese architecture review in `architecture-review.md`.

## Core Conclusion

The business loop is conceptually simple, but runtime/orchestration can become heavy if not isolated:

- Core loop: `Scout -> Manager -> Critic -> Experiment`
- Desired layering: `orchestration` / `runtime` / `presentation`

## Implemented Progress (as of 2026-03-10)

P0/P1/P2 recommendations were largely implemented:

- `research_loop.py` extracted as core loop
- typed events unified for TUI and headless
- CLI surface simplified to higher-level concepts (`mode`, `workers`, `goal`)
- default backlog path simplified (`IdeaBacklog` vs parallel `IdeaPool`)
- advanced runtime features isolated behind parallel/runtime profiles
- `events.jsonl` is canonical runtime/control stream; `control.json` is compatibility snapshot

## Remaining Priorities

### R1

- Continue thinning `run_cmd.py` adapter/lifecycle responsibilities
- Further internalize role-program concepts (reduce external cognitive surface)

### R2

- Keep advanced runtime profile/observability boundaries explicit
- Reduce doc drift between current canonical behavior and historical plans

## Current Architectural Shape

### Default path (single worker)

`CLI adapters -> ResearchLoop -> typed events -> TUI/Headless renderers`

### Advanced path (`workers > 1`)

`parallel_runtime -> WorkerManager -> runtime plugins -> IdeaPool claim/token flow`

## Documentation Contract

When historical plan docs conflict with implementation snapshots:

1. treat source code behavior as authoritative
2. treat canonical docs (`architecture-review.*`, `repo_inventory.*`) as current intent
3. treat `docs/plans/` as historical archive
