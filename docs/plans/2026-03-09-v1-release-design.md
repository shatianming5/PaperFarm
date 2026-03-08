# Open Researcher v1.0 Release Design

## Goal

Transform open-researcher from a 565-line MVP into a production-ready, publishable CLI framework that lets AI agents run automated experiments in **any** repo. Target: viral launch potential on HN/Twitter/Reddit.

## Core Positioning

**"Let AI agents run experiments in any repo while you sleep."**

Unlike karpathy/autoresearch (single-repo, fixed format), open-researcher works with any git repository and any AI agent.

## Architecture Overview

```
open-researcher (CLI)
├── init          → Initialize .research/ with templates
├── run           → Launch AI agent with program.md (NEW - core feature)
├── status        → Real-time TUI progress display (UPGRADED)
├── results       → Print results.tsv
├── dashboard     → Web dashboard
└── export        → Export experiment report
```

Key addition: **Agent integration layer** — the `run` command launches an AI agent (Claude Code, codex-cli, aider, opencode) in subprocess, feeds it program.md, and shows real-time progress via Rich TUI.

---

## Module 1: Agent Integration Layer

### New module: `src/open_researcher/agents/`

```
agents/
├── __init__.py       # Registry + auto-detection
├── base.py           # AgentAdapter abstract base class
├── claude_code.py    # Claude Code adapter
├── codex.py          # codex-cli adapter
├── aider.py          # aider adapter
└── opencode.py       # opencode adapter
```

### AgentAdapter Interface

```python
class AgentAdapter(ABC):
    name: str           # "claude-code"
    command: str        # "claude" (binary name)

    @abstractmethod
    def check_installed(self) -> bool:
        """Check if agent binary is available (shutil.which)."""

    @abstractmethod
    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        """Build the subprocess command to launch the agent."""

    @abstractmethod
    def run(self, workdir: Path, on_output: Callable[[str], None]) -> int:
        """Launch agent subprocess, stream output via callback, return exit code."""
```

### Agent-specific launch strategies

| Agent | Launch Method |
|-------|--------------|
| Claude Code | `claude -p "$(cat program.md)" --allowedTools Edit,Write,Bash,Read` |
| codex-cli | `codex exec -c "$(cat program.md)"` |
| aider | `aider --message-file program.md` |
| opencode | `opencode -p "$(cat program.md)"` |

### CLI `run` command

```
open-researcher run                        # auto-detect installed agent
open-researcher run --agent claude-code    # specify agent
open-researcher run --agent codex          # use codex
open-researcher run --timeout 3600         # custom timeout
open-researcher run --dry-run              # show command without executing
```

---

## Module 2: TUI Real-time Progress

### Upgrade status from one-shot print to Rich Live display during `run`

```
┌──────────────── Open Researcher ─────────────────┐
│ Phase: 4 - Experiment Loop      Agent: claude-code│
│ Branch: research/mar9           Mode: autonomous  │
├──────────────────────────────────────────────────-─┤
│ Experiments: 5 | 2 kept | 2 discarded | 1 crash   │
│ Primary: test_acc ↑  Best: 87.3%  Baseline: 82.1% │
├──────────────────────────────────────────────────-─┤
│ #5 [keep]    ResNet18+dropout  test_acc=87.3%      │
│ #4 [discard] larger_lr         test_acc=79.1%      │
│ #3 [keep]    batch_norm        test_acc=85.4%      │
├──────────────── Agent Output ────────────────────-─┤
│ > Running experiment: cosine annealing scheduler   │
│ > Training epoch 3/10... loss=0.342                │
└──────────────────────────────────────────────────-─┘
```

Implementation:
- `Rich.Live` + `Rich.Layout` for real-time TUI
- Top panel: stats from results.tsv (polled every 2s via file mtime check)
- Bottom panel: scrolling agent stdout/stderr (last 10 lines)
- Refresh rate: 1 second

---

## Module 3: Project Infrastructure

### README.md
- Hero section with tagline + GIF
- Comparison table vs autoresearch
- Quick Start (3 commands)
- Agent support matrix
- Examples section linking to demos

### Files to add
- `LICENSE` (MIT)
- `.gitignore` (Python standard)
- `CONTRIBUTING.md` (brief)
- `Makefile` (dev shortcuts: test, lint, install)
- `.github/workflows/ci.yml` (lint + test on push, Python 3.10-3.13)

### pyproject.toml updates
- Add authors, license, classifiers, readme, homepage, repository
- Add `[project.optional-dependencies]` for dev (pytest, httpx, ruff)
- Add `[tool.ruff]` and `[tool.pytest.ini_options]`

### Internationalization
- All UI text in English (status_cmd.py currently has Chinese)
- Optional `README.zh-CN.md`

### Test fixes
- Remove hardcoded absolute path in test_record.py
- Add CLI-level tests (typer CliRunner)
- Add agent adapter tests (mocked subprocess)
- Target: 90%+ test coverage on core modules

---

## Module 4: Demo Cases (Real Known Repos)

### Demo 1: Triton Kernel Optimization — `linkedin/Liger-Kernel`
- LinkedIn's efficient Triton kernels for LLM training (3K+ stars)
- Metric: kernel throughput / TFLOPS (higher_is_better)
- AI tries: tiling strategies, memory access patterns, operator fusion
- Pre-configured .research/ with evaluation design

### Demo 2: NLP Model Improvement — `karpathy/nanoGPT`
- Most popular minimal GPT implementation (~35K stars)
- Metric: val_loss (lower_is_better)
- AI tries: architecture variants, lr schedules, positional encoding
- Pre-configured .research/ with evaluation design

### Demo 3: ML Fine-tuning — HuggingFace Transformers GLUE task
- Real-world fine-tuning on SST-2 sentiment classification
- Metric: eval_accuracy (higher_is_better)
- AI tries: hyperparameter search, lr strategies, data augmentation
- Pre-configured .research/ with evaluation design

Each demo provides:
- `examples/<repo-name>/README.md` — reproduction steps
- `examples/<repo-name>/.research/` — pre-configured research environment
- `examples/<repo-name>/results-sample.tsv` — sample experiment records

---

## Priority Order (Tonight)

1. **Agent integration layer** (agents/ module + run command) — core feature
2. **TUI real-time progress** — wow moment
3. **Internationalization + test fixes** — code quality
4. **README + project infrastructure** — publishability
5. **Demo cases** (at least 1 complete end-to-end) — proof it works
6. **CI + PyPI readiness** — professional quality

## Non-Goals (Future Versions)

- Dashboard WebSocket upgrade (keep polling for now)
- Plugin marketplace
- Cloud deployment
- Multi-agent orchestration
- Experiment comparison UI
