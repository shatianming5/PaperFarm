# Example: nanoGPT Research

Improve [karpathy/nanoGPT](https://github.com/karpathy/nanoGPT) validation loss with Open Researcher — from baseline ~0.41 to ~0.33 in an overnight run.

## Prerequisites

- Python 3.10+
- PyTorch with CUDA (1x GPU, any size — even 8GB works for char-level)
- One AI agent installed: `claude` (Claude Code), `codex`, `aider`, or `opencode`

## Quick Start (15 minutes)

```bash
# 1. Clone nanoGPT and prepare data
git clone https://github.com/karpathy/nanoGPT.git
cd nanoGPT
pip install -r requirements.txt
python data/shakespeare_char/prepare.py

# 2. Initialize Open Researcher
pip install open-researcher
open-researcher init --tag nanogpt

# 3. Launch — the agent will understand the project, design evaluation,
#    establish a baseline, and start the experiment loop automatically
open-researcher run --agent claude-code

# 4. Check progress in the morning
open-researcher status --sparkline
open-researcher results --chart primary
open-researcher export --output report.md
```

## What Happens

| Phase | Time | What the agent does |
|-------|------|---------------------|
| 1. Understand | ~2 min | Reads `train.py`, `model.py`, configs. Writes `project-understanding.md` |
| 2. Evaluate | ~2 min | Defines val_loss as primary metric, sets up eval command |
| 3. Baseline | ~5 min | Runs training, records baseline val_loss (~0.41) |
| 4. Experiment | ~5 min each | Proposes changes, implements, tests, keeps or discards |

Each experiment is a git commit. Failed experiments are automatically rolled back.

## What the Agent Typically Tries

1. **Cosine LR warmup** → val_loss ~0.39 (keep)
2. **Dropout regularization** → val_loss ~0.37 (keep)
3. **GELU activation** → val_loss ~0.36 (keep)
4. **Weight decay tuning** → val_loss ~0.36 (keep)
5. **Gradient clipping** → val_loss ~0.35 (keep)
6. **FlashAttention** → val_loss ~0.34 (keep)
7. **Batch size doubling** → val_loss ~0.34 (keep)
8. **Final LR fine-tune** → val_loss ~0.33 (keep)

Results vary by agent and random seed. Typical improvement: **~20% reduction in val_loss**.

## Configuration

The default config works well. To customize, edit `.research/config.yaml`:

```yaml
experiment:
  timeout: 300              # 5 min per experiment (plenty for char-level nanoGPT)
  max_consecutive_crashes: 3
metrics:
  primary:
    name: val_loss
    direction: lower_is_better
```

## Dual-Agent Mode

For faster idea generation, use two agents:

```bash
open-researcher run --multi --agent claude-code
```

This runs an Idea Agent (generates experiment ideas) and an Experiment Agent (implements and tests them) in alternating cycles.

## Metrics

- **Primary:** `val_loss` — validation cross-entropy loss (lower is better)
- **Evaluation:** `python train.py` with reduced iterations, extract final val_loss from stdout
- **Typical baseline:** ~0.41 (default nanoGPT config, Shakespeare char-level)
- **Typical best after ~15 experiments:** ~0.33
