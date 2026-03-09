# Changelog

All notable changes to Open Researcher will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `open-researcher demo` command — experience the TUI with sample data, no agent needed
- Agent adapter configurability via `config.yaml` `agents:` section (model, flags, tools)
- Git worktree isolation for parallel experiment workers
- Issue and PR templates for GitHub
- This changelog

### Fixed
- Parallel workers now run in isolated git worktrees instead of sharing the main repo
- `agent_factory` creates fresh agent instances per worker (was sharing single instance)
- `cfg.worker_agent` config field is now respected (was ignored)
- `build_command` and `run` methods are now consistent in all adapters
- Thread-safe output callback with proper log file cleanup

## [0.2.0b1] - 2026-03-09

### Added
- 5-tab Textual TUI dashboard (Overview, Ideas, Charts, Logs, Docs)
- Dual-agent mode (`--multi`): Idea Agent + Experiment Agent
- Parallel GPU workers with `WorkerManager`
- CLI subcommands: `ideas`, `config`, `logs`
- Terminal charts via plotext (`results --chart`, `status --sparkline`)
- Runtime controls: timeout watchdog, crash counter, phase gate
- `doctor` command for environment health checks
- `export` command for Markdown reports

## [0.1.0] - 2026-03-08

### Added
- Initial release
- `init` command to set up `.research/` directory
- `run` command with single-agent mode
- Support for Claude Code, Codex, Aider, OpenCode agents
- `status` and `results` commands
- Automated 5-phase research workflow (understand → literature → evaluate → baseline → experiment loop)
