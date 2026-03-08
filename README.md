# Open Researcher 🔬

> **Let AI agents run experiments in any repo while you sleep.**

Open Researcher is a CLI framework that sets up automated research workflows in any git repository. Point it at your project, pick an AI agent, and let it autonomously understand your code, design evaluation metrics, establish baselines, and run experiments — keeping what works, discarding what doesn't.

Unlike tools locked to specific repo formats, Open Researcher works with **any** project — ML training, performance optimization, algorithm design, or anything with measurable outcomes.

## Quick Start

```bash
pip install open-researcher

cd your-project
open-researcher init
open-researcher run --agent claude-code
# Go to sleep. Check results in the morning:
open-researcher status
```

## How It Works

Open Researcher generates a `.research/` directory in your repo with:

| File | Purpose |
|------|---------|
| `program.md` | Agent instructions — the 4-phase research workflow |
| `config.yaml` | Mode (autonomous/collaborative), metrics, timeout |
| `project-understanding.md` | Agent fills this: what the project does |
| `evaluation.md` | Agent fills this: how to measure improvement |
| `results.tsv` | Experiment log (timestamp, commit, metrics, status) |
| `scripts/record.py` | Record experiment results |
| `scripts/rollback.sh` | Discard failed experiments |

### The 4-Phase Workflow

1. **Understand Project** — Agent reads your code, docs, tests. Writes `project-understanding.md`.
2. **Design Evaluation** — Agent defines metrics (what to optimize, how to measure). Writes `evaluation.md`.
3. **Establish Baseline** — Run current code, record baseline metrics.
4. **Experiment Loop** — Propose idea → implement → test → evaluate → keep or discard. Repeat.

Each experiment is a git commit. Successful experiments stay; failed ones are rolled back. Everything is logged in `results.tsv`.

## Supported Agents

| Agent | Command | Status |
|-------|---------|--------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `--agent claude-code` | ✅ Supported |
| [Codex CLI](https://github.com/openai/codex) | `--agent codex` | ✅ Supported |
| [Aider](https://github.com/paul-gauthier/aider) | `--agent aider` | ✅ Supported |
| [OpenCode](https://github.com/opencode-ai/opencode) | `--agent opencode` | ✅ Supported |

Auto-detection: If you don't specify `--agent`, Open Researcher will find the first installed agent.

## Commands

```bash
open-researcher init [--tag NAME]               # Initialize .research/ directory
open-researcher run [--agent NAME] [--dry-run]   # Launch AI agent
open-researcher status                           # Show experiment progress
open-researcher results                          # Print results table
open-researcher export                           # Export markdown report
open-researcher dashboard [--port 8384]          # Launch web dashboard
```

## Web Dashboard

```bash
open-researcher dashboard
# Open http://localhost:8384
```

Dark-themed dashboard with:
- Real-time experiment statistics
- Metric trend chart (Chart.js)
- Experiment history table
- Document viewer (project understanding, evaluation design)

## Comparison with autoresearch

| Feature | autoresearch | Open Researcher |
|---------|-------------|-----------------|
| Works with any repo | ❌ Fixed 3-file format | ✅ Any git repo |
| Agent support | Claude Code only | Claude Code, Codex, Aider, OpenCode |
| Auto project understanding | ❌ Manual | ✅ Agent-driven |
| Auto evaluation design | ❌ Manual | ✅ Agent-driven |
| Real-time TUI progress | ❌ | ✅ Rich live display |
| Web dashboard | ❌ | ✅ Built-in |
| Intervention modes | Autonomous only | Autonomous + Collaborative |
| `pip install` | ❌ | ✅ |

## Configuration

Edit `.research/config.yaml`:

```yaml
mode: autonomous          # autonomous | collaborative
experiment:
  timeout: 600            # seconds per experiment
  max_consecutive_crashes: 3
metrics:
  primary:
    name: ""              # filled by agent (e.g., "test_acc")
    direction: ""         # higher_is_better | lower_is_better
environment: |
  # Describe your execution environment
  # e.g., Python 3.11, CUDA 12.1, 1x A100
```

## Examples

See [`examples/`](examples/) for complete demo setups:

- **Triton Kernel Optimization** — Optimize GPU kernels in [Liger-Kernel](https://github.com/linkedin/Liger-Kernel)
- **NLP Model Training** — Improve [nanoGPT](https://github.com/karpathy/nanoGPT) validation loss
- **ML Fine-tuning** — Optimize HuggingFace Transformers GLUE benchmark

## Development

```bash
git clone https://github.com/open-researcher/open-researcher.git
cd open-researcher
make dev    # install with dev dependencies
make test   # run tests
make lint   # run linter
```

## License

MIT — see [LICENSE](LICENSE).
