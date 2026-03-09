"""Implementation of the 'status' command."""

import csv
import subprocess
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel


def _has_real_content(path: Path) -> bool:
    """Check if a markdown file has real content beyond headings and comments."""
    if not path.exists():
        return False
    content = path.read_text()
    if "<!--" in content and content.strip().endswith("-->"):
        return False
    return any(
        line.strip()
        and not line.startswith("#")
        and not line.startswith(">")
        and "<!--" not in line
        and not line.startswith("|")
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
        rows = list(csv.DictReader(results.open(), delimiter="\t"))
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
        config = yaml.safe_load(config_path.read_text()) or {}
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
        rows = list(csv.DictReader(results_path.open(), delimiter="\t"))

    state["total"] = len(rows)
    state["keep"] = sum(1 for r in rows if r["status"] == "keep")
    state["discard"] = sum(1 for r in rows if r["status"] == "discard")
    state["crash"] = sum(1 for r in rows if r["status"] == "crash")
    state["recent"] = rows[-5:] if rows else []

    # Compute metric values
    higher = state["direction"] == "higher_is_better"
    keep_rows = [r for r in rows if r["status"] == "keep"]
    if keep_rows:
        values = [float(r["metric_value"]) for r in keep_rows]
        state["baseline_value"] = values[0]
        state["current_value"] = values[-1]
        state["best_value"] = max(values) if higher else min(values)
    else:
        state["baseline_value"] = None
        state["current_value"] = None
        state["best_value"] = None

    state["phase"] = _detect_phase(research)

    # Git branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )
    state["branch"] = result.stdout.strip() if result.returncode == 0 else "unknown"

    return state


PHASE_NAMES = {
    1: "Phase 1: Understand Project",
    2: "Phase 2: Research Related Work",
    3: "Phase 3: Design Evaluation",
    4: "Phase 4: Establish Baseline",
    5: "Phase 5: Experiment Loop",
}


def print_status(repo_path: Path) -> None:
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
            icon = status_icons.get(r["status"], "?")
            val = float(r["metric_value"])
            lines.append(f"    {icon} {val:.4f}  {r['description']}")
    else:
        lines.append("  No experiments yet")

    panel = Panel(
        "\n".join(lines),
        title="Open Researcher",
        border_style="blue",
    )
    console.print(panel)

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
