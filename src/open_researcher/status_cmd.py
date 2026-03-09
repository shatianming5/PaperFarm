"""Implementation of the 'status' command."""

import csv
import math
import subprocess
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel


def _safe_float(value: str) -> float | None:
    """Parse a string to float, returning None for non-numeric or NaN values."""
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


def _has_real_content(path: Path) -> bool:
    """Check if a markdown file has real content beyond headings and comments."""
    if not path.exists():
        return False
    content = path.read_text()
    if "<!--" in content and content.strip().endswith("-->"):
        return False
    return any(
        line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith(">")
        and "<!--" not in line
        and not line.strip().startswith("|")
        for line in content.splitlines()
    )


def _detect_phase(research: Path) -> int:
    """Detect current research phase (1-5) based on file contents."""
    pu = research / "project-understanding.md"
    lit = research / "literature.md"
    ev = research / "evaluation.md"
    results = research / "results.tsv"

    # Phase 1: project understanding not filled
    if not _has_real_content(pu):
        return 1

    # Phase 2: literature review not filled
    if not _has_real_content(lit):
        return 2

    # Phase 3: evaluation not filled
    if not _has_real_content(ev):
        return 3

    # Phase 4/5: check results
    if results.exists():
        with results.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        if len(rows) == 0:
            return 4
        return 5

    return 4


def parse_research_state(repo_path: Path) -> dict:
    """Parse .research/ directory into a state dict."""
    research = repo_path / ".research"
    state = {}

    # Parse config
    config_path = research / "config.yaml"
    if config_path.exists():
        try:
            config = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError:
            config = {}
        state["mode"] = config.get("mode", "autonomous")
        metrics = config.get("metrics", {}).get("primary", {})
        state["primary_metric"] = metrics.get("name", "")
        state["direction"] = metrics.get("direction", "")
    else:
        state["mode"] = "unknown"
        state["primary_metric"] = ""
        state["direction"] = ""

    # Parse results
    results_path = research / "results.tsv"
    rows = []
    if results_path.exists():
        with results_path.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))

    state["total"] = len(rows)
    state["keep"] = sum(1 for r in rows if r.get("status") == "keep")
    state["discard"] = sum(1 for r in rows if r.get("status") == "discard")
    state["crash"] = sum(1 for r in rows if r.get("status") == "crash")
    state["recent"] = rows[-5:] if rows else []

    # Compute metric values — skip rows with non-numeric or NaN metrics
    # Default to higher_is_better when direction is empty (consistent with results_cmd.py)
    higher = state["direction"] != "lower_is_better"
    keep_rows = [r for r in rows if r.get("status") == "keep"]
    values = []
    for r in keep_rows:
        v = _safe_float(r.get("metric_value", ""))
        if v is not None:
            values.append(v)
    if values:
        state["baseline_value"] = values[0]
        state["current_value"] = values[-1]
        state["best_value"] = max(values) if higher else min(values)
    else:
        state["baseline_value"] = None
        state["current_value"] = None
        state["best_value"] = None

    state["phase"] = _detect_phase(research)

    # Git branch
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=5,
        )
        state["branch"] = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (subprocess.TimeoutExpired, OSError):
        state["branch"] = "unknown"

    return state


PHASE_NAMES = {
    1: "Phase 1: Understand Project",
    2: "Phase 2: Research Related Work",
    3: "Phase 3: Design Evaluation",
    4: "Phase 4: Establish Baseline",
    5: "Phase 5: Experiment Loop",
}

SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def _sparkline(values: list[float]) -> str:
    """Generate a Unicode sparkline from a list of values."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if lo == hi:
        return SPARK_CHARS[4] * len(values)
    return "".join(
        SPARK_CHARS[min(int((v - lo) / (hi - lo) * 7), 7)]
        for v in values
    )


def print_status(repo_path: Path, sparkline: bool = False) -> None:
    """Print formatted research status to terminal."""
    research = repo_path / ".research"
    if not research.exists():
        print("[ERROR] No .research/ directory found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    state = parse_research_state(repo_path)
    console = Console()

    lines = []
    lines.append(f"  Phase: {PHASE_NAMES.get(state['phase'], 'unknown')}")
    lines.append(f"  Branch: {state['branch']}")
    lines.append(f"  Mode: {state['mode']}")
    lines.append("")

    if state["total"] > 0:
        lines.append("  Experiments:")
        lines.append(
            f"    Total: {state['total']}  "
            f"✓ keep: {state['keep']}  "
            f"✗ discard: {state['discard']}  "
            f"💥 crash: {state['crash']}"
        )
        lines.append("")

        if state["primary_metric"]:
            lines.append(f"  Primary Metric: {state['primary_metric']}")
            if state["baseline_value"] is not None:
                lines.append(f"    Baseline:  {state['baseline_value']:.4f}")
                lines.append(f"    Current:  {state['current_value']:.4f}")
                lines.append(f"    Best:  {state['best_value']:.4f}")
            lines.append("")

        lines.append(f"  Recent {len(state['recent'])} experiments:")
        status_icons = {"keep": "✓", "discard": "✗", "crash": "💥"}
        for r in reversed(state["recent"]):
            icon = status_icons.get(r.get("status", ""), "?")
            val = _safe_float(r.get("metric_value", ""))
            val_str = f"{val:.4f}" if val is not None else r.get("metric_value", "N/A")
            lines.append(f"    {icon} {val_str}  {r.get('description', '')}")
    else:
        lines.append("  No experiments yet")

    panel = Panel(
        "\n".join(lines),
        title="Open Researcher",
        border_style="blue",
    )
    console.print(panel)

    # Show sparkline if requested
    if sparkline:
        # Collect metric values from keep-status experiments
        results_path = research / "results.tsv"
        keep_values: list[float] = []
        if results_path.exists():
            with results_path.open() as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    if r.get("status") == "keep":
                        v = _safe_float(r.get("metric_value", ""))
                        if v is not None:
                            keep_values.append(v)
        if keep_values:
            console.print(f"  Trend: {_sparkline(keep_values)}")

    # Show agent activity if available
    activity_path = research / "activity.json"
    if activity_path.exists():
        from open_researcher.activity import ActivityMonitor

        monitor = ActivityMonitor(research)
        all_act = monitor.get_all()
        if all_act:
            act_lines = ["  Agent Activity:"]
            for key, act in all_act.items():
                a_status = act.get("status", "idle")
                detail = act.get("detail", "")
                act_lines.append(f"    {key}: [{a_status}] {detail}")
            console.print(Panel("\n".join(act_lines), title="Agents", border_style="green"))
