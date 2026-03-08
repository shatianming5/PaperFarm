# Example: nanoGPT Research

This example shows how to use Open Researcher with [karpathy/nanoGPT](https://github.com/karpathy/nanoGPT) to automatically improve language model training.

## Setup

```bash
# Clone nanoGPT
git clone https://github.com/karpathy/nanoGPT.git
cd nanoGPT
pip install -r requirements.txt

# Prepare data
python data/shakespeare_char/prepare.py

# Initialize Open Researcher (or copy the pre-configured .research/)
open-researcher init --tag nanogpt

# Launch research
open-researcher run --agent claude-code
```

## What the Agent Will Try

- Learning rate schedules (cosine, linear warmup)
- Model architecture changes (layers, heads, embedding dim)
- Regularization (dropout, weight decay tuning)
- Training optimizations (gradient accumulation, mixed precision)
- Data preprocessing improvements

## Metrics

- **Primary:** `val_loss` (lower is better)
- **Evaluation:** Run `python train.py` with reduced iterations, extract final val_loss

## Sample Results

See `results-sample.tsv` for example experiment outcomes.
