# Evaluation Design

## Primary Metric
- **Name:** val_loss
- **Direction:** lower_is_better
- **How to measure:** Run training with reduced iterations, extract final validation loss from stdout.

## Evaluation Command
```bash
python train.py config/train_shakespeare_char.py \
  --max_iters=500 --eval_interval=500 --eval_iters=20 2>&1 | \
  grep "val loss" | tail -1 | awk '{print $NF}'
```

## Secondary Metrics
- `train_loss` — Training loss at evaluation time
- `tokens_per_sec` — Training throughput

## Baseline Method
Run the unmodified training script with default Shakespeare char config for 500 iterations.
