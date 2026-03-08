#!/usr/bin/env python3
"""Record an experiment result to .research/results.tsv."""

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_git_short_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description="Record experiment result")
    parser.add_argument("--metric", required=True, help="Primary metric name")
    parser.add_argument("--value", required=True, type=float, help="Metric value")
    parser.add_argument("--secondary", default="{}", help="Secondary metrics as JSON")
    parser.add_argument("--status", required=True, choices=["keep", "discard", "crash"], help="Experiment status")
    parser.add_argument("--desc", required=True, help="Brief description")
    args = parser.parse_args()

    # Find .research/results.tsv relative to git root
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    ).stdout.strip()
    results_path = Path(git_root) / ".research" / "results.tsv"

    header = ["timestamp", "commit", "primary_metric", "metric_value", "secondary_metrics", "status", "description"]

    # Create file with header if it doesn't exist
    if not results_path.exists():
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with results_path.open("w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(header)

    # Append row
    row = [
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        get_git_short_hash(),
        args.metric,
        f"{args.value:.6f}",
        args.secondary,
        args.status,
        args.desc,
    ]
    with results_path.open("a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(row)

    print(f"[OK] Recorded: {args.status} | {args.metric}={args.value:.6f} | {args.desc}")


if __name__ == "__main__":
    main()
