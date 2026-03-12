# Contributing to PaperFarm

[English](CONTRIBUTING.md) · [简体中文](CONTRIBUTING.zh-CN.md)

Thanks for your interest in contributing.

## Before You Start

- Prefer **issue first, PR second** for non-trivial changes.
- Keep changes scoped: one feature/fix per PR.
- If behavior changes, update docs and add/adjust tests in the same PR.

## Development Setup

```bash
git clone https://github.com/shatianming5/PaperFarm.git
cd PaperFarm
python -m venv .venv
source .venv/bin/activate
make dev
```

## Local Checks

```bash
make lint
make test
make test-cov
make package-check
make ci
```

`make ci` is the expected pre-PR baseline.

## Pull Request Checklist

- Clear PR title and description (what changed and why)
- Linked issue (for non-trivial changes)
- Tests updated or added when behavior changes
- Docs updated when UX/CLI/config/contracts change
- No unrelated refactors mixed into the same PR

## Documentation Policy

Core contributor-facing docs should stay bilingual (EN/ZH):

- `README.md` / `README.zh-CN.md`
- `CONTRIBUTING.md` / `CONTRIBUTING.zh-CN.md`
- `docs/README.md` / `docs/README.zh-CN.md`

Historical plan docs under `docs/plans/` are archived and not the canonical interface contract.

## Code Style

We use [ruff](https://github.com/astral-sh/ruff) for linting/formatting.

```bash
make lint
make format
```

## Adding a New Agent Adapter

1. Add `src/open_researcher/agents/<agent>.py`
2. Implement `AgentAdapter` (see `src/open_researcher/agents/base.py`)
3. Register adapter via `@register`
4. Add tests in `tests/test_agents.py`
5. Update agent docs in `README.md` and `README.zh-CN.md`
