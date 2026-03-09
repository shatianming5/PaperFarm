# Open Researcher

> **Let AI agents run experiments in any repo while you sleep.**

Open Researcher is a CLI framework that sets up automated research workflows in any git repository. Point it at your project, pick an AI agent, and let it autonomously understand your code, design evaluation metrics, establish baselines, and run experiments — keeping what works, discarding what doesn't.

Unlike tools locked to specific repo formats, Open Researcher works with **any** project — ML training, performance optimization, algorithm design, or anything with measurable outcomes.

## See It in Action

Try the interactive demo — no agent or API key needed:

```bash
pip install open-researcher
open-researcher demo
```

<!-- TUI Dashboard Screenshot — replace with actual screenshot/GIF -->
```
┌─ Open Researcher ──────────────────────────────────────────────────────┐
│ Experiments: 15 │ Kept: 10 │ Discarded: 3 │ Crashed: 1 │ Best: 0.329 │
├─ Overview ─ Ideas ─ Charts ─ Logs ─ Docs ──────────────────────────────┤
│                                                                        │
│  ▌ Experiment Agent  experimenting                                     │
│  ▌ Running: sliding window attention (idea-003)                        │
│  ▌ ████████████████████░░░░░░░░  62%  (5/8 ideas)                     │
│                                                                        │
│  Recent Experiments:                                                   │
│  #15  final-tune      keep     val_loss=0.329  ↓ Fine-tune LR 1e-5    │
│  #14  kv-cache        keep     val_loss=0.335  ↓ KV-cache optim       │
│  #13  mixup-aug       discard  val_loss=0.355  ↑ MixUp augmentation   │
│  #12  batch-x2        keep     val_loss=0.338  ↓ Double batch size    │
│  #11  flash-attn      keep     val_loss=0.343  ↓ FlashAttention-2     │
│                                                                        │
│  [p]ause [r]esume [s]kip [a]dd idea [g]pu [q]uit                      │
└────────────────────────────────────────────────────────────────────────┘
```

**5 tabs**: Overview (stats + progress) · Ideas (pool management) · Charts (metric trends) · Logs (live agent output with diff coloring) · Docs (project understanding, literature, evaluation)

<!-- TODO: Replace the ASCII mockup above with actual screenshot/GIF:
     1. Run `open-researcher demo`
     2. Record with asciinema: `asciinema rec demo.cast`
     3. Convert to GIF: `agg demo.cast demo.gif`
     4. Replace this block with: ![TUI Dashboard](docs/assets/demo.gif)
-->

## Quick Start

```bash
pip install open-researcher

cd your-project
open-researcher init
open-researcher run --agent claude-code
# Go to sleep. Check results in the morning:
open-researcher status --sparkline
open-researcher results --chart primary
```

## How It Works

Open Researcher generates a `.research/` directory in your repo with:

| File | Purpose |
|------|---------|
| `program.md` | Agent instructions — the 4-phase research workflow |
| `config.yaml` | Mode (autonomous/collaborative), metrics, timeout, agent settings |
| `project-understanding.md` | Agent fills this: what the project does |
| `evaluation.md` | Agent fills this: how to measure improvement |
| `results.tsv` | Experiment log (timestamp, commit, metrics, status) |
| `scripts/record.py` | Record experiment results |
| `scripts/rollback.sh` | Discard failed experiments |

### The 4-Phase Workflow

1. **Understand Project** — Agent reads your code, docs, tests. Writes `project-understanding.md`.
2. **Design Evaluation** — Agent defines metrics (what to optimize, how to measure). Writes `evaluation.md`.
3. **Establish Baseline** — Run current code, record baseline metrics.
4. **Experiment Loop** — Propose idea, implement, test, evaluate, keep or discard. Repeat.

Each experiment is a git commit. Successful experiments stay; failed ones are rolled back. Everything is logged in `results.tsv`.

## Safety First

Open Researcher treats your repo with care:

- Every experiment is an **isolated git commit** — nothing is lost
- Failed experiments are **automatically rolled back** via `git reset`
- **Timeout watchdog** kills runaway experiments
- **Crash counter** auto-pauses after N consecutive failures
- **Collaborative mode** pauses for human review between phases
- Parallel workers run in **isolated git worktrees** — they can't interfere with each other

## Supported Agents

| Agent | Command | Status |
|-------|---------|--------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `--agent claude-code` | Supported |
| [Codex CLI](https://github.com/openai/codex) | `--agent codex` | Supported |
| [Aider](https://github.com/paul-gauthier/aider) | `--agent aider` | Supported |
| [OpenCode](https://github.com/opencode-ai/opencode) | `--agent opencode` | Supported |

Auto-detection: If you don't specify `--agent`, Open Researcher finds the first installed one.

### Agent Configuration

Customize agent parameters in `.research/config.yaml`:

```yaml
agents:
  claude-code:
    model: "claude-sonnet-4-5-20250514"   # override model
    allowed_tools: "Edit,Write,Bash,Read,Glob,Grep"
    extra_flags: ["--max-turns", "50"]
  codex:
    model: "gpt-5.2"                      # override default gpt-5.3-codex
    sandbox: "suggest"                     # full-auto | suggest | ask
  aider:
    model: "gpt-4o"
    extra_flags: ["--no-git"]
```

## Commands

```bash
open-researcher demo                        # Try the TUI with sample data (no agent needed!)
open-researcher init [--tag NAME]           # Initialize .research/ directory
open-researcher run [--agent NAME]          # Launch AI agent with TUI dashboard
open-researcher run --multi                 # Dual-agent mode (idea + experiment)
open-researcher status [--sparkline]        # Show experiment progress
open-researcher results [--chart primary]   # Print results table or chart
open-researcher export [--output FILE]      # Export markdown report
open-researcher doctor                      # Health check environment
open-researcher ideas list                  # Manage idea pool
open-researcher config show                 # View/validate configuration
open-researcher logs [--follow] [--errors]  # View agent logs
```

## Interactive TUI Dashboard

```bash
open-researcher run --agent claude-code
```

Rich terminal dashboard with 5 tabs:

- **Overview** — Real-time stats, agent status with progress bar, recent results
- **Ideas** — Idea pool with status, priority, category, metric values
- **Charts** — Metric trend visualization with keep/discard/crash coloring
- **Logs** — Live agent output with diff highlighting and thinking/acting phases
- **Docs** — View project understanding, literature, evaluation design

Keyboard shortcuts: `1-5` switch tabs, `p` pause, `r` resume, `s` skip, `a` add idea, `g` GPU status, `q` quit.

## Runtime Controls

- **Timeout watchdog** — Kills experiments exceeding the configured time limit
- **Crash counter** — Auto-pauses after N consecutive crashes
- **Collaborative mode** — Pauses for human review between phases
- **Parallel workers** — Run experiments across multiple GPUs in isolated worktrees

## Comparison with autoresearch

| Feature | autoresearch | Open Researcher |
|---------|-------------|-----------------|
| Works with any repo | Fixed 3-file format | **Any git repo** |
| Agent support | Claude Code only | **Claude Code, Codex, Aider, OpenCode** |
| Agent configurability | Hardcoded | **Per-agent model, flags, tools via config** |
| Auto project understanding | Manual | **Agent-driven** |
| Auto evaluation design | Manual | **Agent-driven** |
| Interactive TUI dashboard | No | **5-tab terminal dashboard** |
| Terminal charts | No | **plotext metric trends** |
| Runtime controls | No | **Timeout, crash limit, collaborative mode** |
| Parallel experiments | No | **Multi-GPU workers with worktree isolation** |
| Health checks | No | **`doctor` command** |
| Try without setup | No | **`demo` command** |
| `pip install` | No | **Yes** |

## Configuration

Edit `.research/config.yaml`:

```yaml
mode: autonomous          # autonomous | collaborative
experiment:
  timeout: 600            # seconds per experiment before kill
  max_consecutive_crashes: 3
  max_parallel_workers: 0  # 0 = auto (one per GPU), 1 = serial
metrics:
  primary:
    name: ""              # filled by agent (e.g., "val_loss")
    direction: ""         # higher_is_better | lower_is_better
environment: |
  # Describe your execution environment
  # e.g., Python 3.11, CUDA 12.1, 1x A100
agents:                   # per-agent overrides (optional)
  codex:
    model: "gpt-5.3-codex"
```

## Platform Support

macOS, Linux, and Windows (Python 3.10+).

## Examples

See [`examples/`](examples/) for complete setups:

- **[nanoGPT](examples/nanogpt/)** — Reduce validation loss in character-level language model training
- **[Liger-Kernel](examples/liger-kernel/)** — Optimize Triton GPU kernels
- **[HF GLUE](examples/hf-glue/)** — Improve HuggingFace Transformers fine-tuning

## Development

```bash
git clone https://github.com/open-researcher/open-researcher.git
cd open-researcher
make dev    # install with dev dependencies
make test   # run tests
make lint   # run linter
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT — see [LICENSE](LICENSE).
