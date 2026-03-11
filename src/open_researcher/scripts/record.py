#!/usr/bin/env python3
"""Record an experiment result to .research/results.tsv."""

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from filelock import FileLock


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

    try:
        secondary = json.loads(args.secondary)
    except (json.JSONDecodeError, TypeError):
        print(f"[ERROR] --secondary is not valid JSON: {args.secondary}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(secondary, dict):
        print(f"[ERROR] --secondary must decode to a JSON object: {args.secondary}", file=sys.stderr)
        raise SystemExit(1)

    trace = {
        "frontier_id": os.environ.get("OPEN_RESEARCHER_FRONTIER_ID", "").strip(),
        "idea_id": os.environ.get("OPEN_RESEARCHER_IDEA_ID", "").strip(),
        "execution_id": os.environ.get("OPEN_RESEARCHER_EXECUTION_ID", "").strip(),
        "hypothesis_id": os.environ.get("OPEN_RESEARCHER_HYPOTHESIS_ID", "").strip(),
        "experiment_spec_id": os.environ.get("OPEN_RESEARCHER_EXPERIMENT_SPEC_ID", "").strip(),
    }
    trace = {key: value for key, value in trace.items() if value}
    if trace:
        secondary["_open_researcher_trace"] = trace
    secondary["_open_researcher_result_id"] = uuid4().hex

    # Find .research/results.tsv relative to git root
    git_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if git_root_result.returncode != 0:
        print("[ERROR] Failed to determine git root. Are you in a git repository?", file=sys.stderr)
        raise SystemExit(1)
    git_root = git_root_result.stdout.strip()
    results_path = Path(git_root) / ".research" / "results.tsv"

    header = ["timestamp", "commit", "primary_metric", "metric_value", "secondary_metrics", "status", "description"]

    # Append row
    row = [
        datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        get_git_short_hash(),
        args.metric,
        f"{args.value:.6f}",
        json.dumps(secondary, separators=(",", ":")),
        args.status,
        args.desc,
    ]

    lock = FileLock(str(results_path) + ".lock")
    with lock:
        # Create file with header if it doesn't exist
        if not results_path.exists():
            results_path.parent.mkdir(parents=True, exist_ok=True)
            with results_path.open("w", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(header)

        with results_path.open("a", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(row)

    print(f"[OK] Recorded: {args.status} | {args.metric}={args.value:.6f} | {args.desc}")


if __name__ == "__main__":
    main()
