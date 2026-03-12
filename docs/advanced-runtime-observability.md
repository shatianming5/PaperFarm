# Advanced Runtime Profiles & Observability

This document defines the `research-v1` boundary between the default serial loop and the advanced parallel runtime.

## Runtime Profiles

Parallel runtime profiles are derived from `config.yaml` (`runtime.*`) and worker count:

- `minimal`: all advanced plugins disabled.
- `custom`: a subset of advanced plugins enabled.
- `advanced`: GPU allocation + failure memory + worktree isolation all enabled.

Key toggles:

- `runtime.gpu_allocation`
- `runtime.failure_memory`
- `runtime.worktree_isolation`
- `experiment.max_parallel_workers`

Notes:

- Worker count is resolved through `resolve_parallel_worker_count` and may be clamped (for example, pinned CUDA visibility without internal allocation).
- `worktree_isolation` is forced on when workers are parallel (`workers > 1`) to keep code workspaces isolated.

## Observability Boundary

Runtime/control observability follows a single-source rule:

- Canonical stream: `.research/events.jsonl`
- Compatibility/derived snapshots: `.research/control.json`, `.research/activity.json`, `.research/gpu_status.json`
- Detached execution registrations: `.research/runtime/*.json`

Operationally:

- Consumers should treat `events.jsonl` as the source of truth.
- Snapshot files are for compatibility, quick reads, and UI conveniences.

## Status Command Output

`open-researcher status` now reports:

- Resolved runtime mode/profile and effective workers
- Plugin boundary (`gpu_allocation`, `failure_memory`, `worktree_isolation`)
- Frontier projection target (when resolvable)
- Canonical event stream health (`event_count`, `last_seq`, parse errors)
- Snapshot presence and detached runtime registration count

This keeps advanced runtime behavior visible without polluting the default serial mental model.
