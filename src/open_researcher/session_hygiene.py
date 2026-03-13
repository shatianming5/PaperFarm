"""Runtime session hygiene helpers for restarting research workflows safely."""

from __future__ import annotations

from pathlib import Path

from open_researcher.activity import ActivityMonitor
from open_researcher.control_plane import issue_control_command, read_control


def reset_runtime_session_state(research_dir: Path, *, source: str) -> dict[str, object]:
    """Clear stale control latches and experiment worker activity for a new runtime session."""
    ctrl_path = research_dir / "control.json"
    state = read_control(ctrl_path)
    resumed = False
    cleared_skip = False

    if bool(state.get("paused", False)):
        issue_control_command(
            ctrl_path,
            command="resume",
            source=source,
            reason="starting new runtime session",
        )
        resumed = True

    state = read_control(ctrl_path)
    if bool(state.get("skip_current", False)):
        issue_control_command(
            ctrl_path,
            command="clear_skip",
            source=source,
            reason="starting new runtime session",
        )
        cleared_skip = True

    activity = ActivityMonitor(research_dir)
    experiment_entry = activity.get("experiment_agent")
    stale_workers = 0
    cleared_workers = False
    if isinstance(experiment_entry, dict):
        workers = experiment_entry.get("workers")
        if isinstance(workers, list):
            stale_workers = len(workers)
        if stale_workers > 0:
            activity.clear_workers("experiment_agent", status="idle", detail="0 active worker(s)", idea="")
            cleared_workers = True

    final_state = read_control(ctrl_path)
    changed = resumed or cleared_skip or cleared_workers
    return {
        "changed": changed,
        "resumed": resumed,
        "cleared_skip": cleared_skip,
        "cleared_workers": cleared_workers,
        "stale_workers": stale_workers,
        "control": final_state,
    }


def describe_runtime_session_reset(summary: dict[str, object]) -> str:
    """Render a compact human-readable summary of startup hygiene actions."""
    actions: list[str] = []
    if bool(summary.get("resumed", False)):
        actions.append("resumed stale pause")
    if bool(summary.get("cleared_skip", False)):
        actions.append("cleared stale skip_current")
    if bool(summary.get("cleared_workers", False)):
        stale_workers = int(summary.get("stale_workers", 0) or 0)
        if stale_workers > 0:
            actions.append(f"cleared {stale_workers} stale experiment worker(s)")
        else:
            actions.append("reset experiment worker activity")
    return ", ".join(actions)
