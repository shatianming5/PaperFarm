# Project Understanding

## Project Goal
nanoGPT is a minimal GPT implementation for training and fine-tuning medium-sized language models. It focuses on simplicity and readability while being performant enough for real experiments.

## Code Structure
- `train.py` — Main training script (single file, ~300 lines)
- `model.py` — GPT model definition (transformer architecture)
- `config/` — Training configurations for different datasets/scales
- `data/` — Dataset preparation scripts (Shakespeare, OpenWebText)
- `sample.py` — Text generation from trained model

## How to Run
```bash
python train.py config/train_shakespeare_char.py
```

## Key Configuration
- `n_layer`, `n_head`, `n_embd` — Model size
- `learning_rate`, `max_iters`, `lr_decay_iters` — Training schedule
- `dropout`, `weight_decay` — Regularization
- `batch_size`, `block_size` — Data loading
