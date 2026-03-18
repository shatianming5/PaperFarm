"""TUI widgets for the PaperFarm command center.

Each widget exposes an ``update_data`` (or ``update_phase``) method that
accepts plain dicts/lists produced by ``ResearchState.summary()``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.containers import Vertical
from textual.widgets import DataTable, RichLog, Static

_PHASES = ("scout", "manager", "critic", "experiment")


def _ts_short(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return "??:??:??"
    return dt.strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# StatsBar
# ---------------------------------------------------------------------------


class StatsBar(Static):
    """Single-line status bar showing key research metrics."""

    def update_data(self, summary: dict[str, Any]) -> None:
        phase = summary.get("phase", "idle")
        rnd = summary.get("round", 0)
        hyps = summary.get("hypotheses", 0)
        done = summary.get("experiments_done", 0)
        total = summary.get("experiments_total", 0)
        running = summary.get("experiments_running", 0)
        best = summary.get("best_value", "\u2014")
        suffix = ""
        if summary.get("paused"):
            suffix = " [bold yellow][PAUSED][/]"
        if phase == "failed":
            phase_str = "[bold red]FAILED[/]"
        elif phase == "crashed":
            phase_str = "[bold red]CRASHED[/]"
        else:
            phase_str = phase
        self.update(
            f"Phase: {phase_str} | Round: {rnd} | Hyps: {hyps} "
            f"| Exps: {done}/{total} ({running}) | Best: {best}{suffix}"
        )


# ---------------------------------------------------------------------------
# PhaseStripBar
# ---------------------------------------------------------------------------


class PhaseStripBar(Static):
    """Horizontal phase indicator highlighting the active phase."""

    def on_mount(self) -> None:
        self._last_phase = ""

    def update_phase(self, phase: str) -> None:
        if phase == self._last_phase:
            return
        self._last_phase = phase
        parts: list[str] = []
        for p in _PHASES:
            if p == phase:
                parts.append(f"[bold green]{p.upper()}[/]")
            else:
                parts.append(f"[dim]{p}[/]")
        # Show terminal states after the pipeline
        if phase in ("failed", "crashed"):
            parts.append(f"  [bold red]\u2717 {phase.upper()}[/]")
        elif phase == "idle":
            pass  # no extra indicator
        self.update("  \u2023  ".join(parts))


# ---------------------------------------------------------------------------
# FrontierPanel
# ---------------------------------------------------------------------------


class FrontierPanel(Vertical):
    """DataTable listing frontier items sorted by priority."""

    def on_mount(self) -> None:
        self._last_ids: list[str] = []

    def compose(self):  # type: ignore[override]
        table = DataTable(id="frontier-table")
        table.add_columns("ID", "Priority", "Status", "Description")
        yield table

    def update_data(self, frontier: list[dict[str, Any]]) -> None:
        items = sorted(frontier, key=lambda f: -float(f.get("priority", 0)))
        new_ids = [str(i.get("id", "")) + str(i.get("status", "")) for i in items]
        if new_ids == self._last_ids:
            return
        self._last_ids = new_ids
        table: DataTable = self.query_one("#frontier-table", DataTable)
        table.clear()
        for item in items:
            table.add_row(
                str(item.get("id", "")),
                str(item.get("priority", "")),
                str(item.get("status", "")),
                str(item.get("description", ""))[:60],
            )


# ---------------------------------------------------------------------------
# WorkerPanel
# ---------------------------------------------------------------------------


class WorkerPanel(Vertical):
    """DataTable showing live worker status."""

    def on_mount(self) -> None:
        self._last_snapshot: list[str] = []

    def compose(self):  # type: ignore[override]
        table = DataTable(id="worker-table")
        table.add_columns("Worker", "Status", "GPU", "Frontier")
        yield table

    def update_data(self, workers: list[dict[str, Any]]) -> None:
        snap = [f"{w.get('id')}-{w.get('status')}" for w in workers]
        if snap == self._last_snapshot:
            return
        self._last_snapshot = snap
        table: DataTable = self.query_one("#worker-table", DataTable)
        table.clear()
        for w in workers:
            table.add_row(
                str(w.get("id", "")),
                str(w.get("status", "")),
                str(w.get("gpu", "")),
                str(w.get("frontier_id", "")),
            )


# ---------------------------------------------------------------------------
# LogPanel
# ---------------------------------------------------------------------------

_EVENT_PREFIXES: dict[str, str] = {
    "skill_started": "[cyan]SKILL[/]",
    "agent_output": "[white]OUT[/]",
    "output": "[white]OUT[/]",
    "worker_started": "[blue]W+[/]",
    "worker_finished": "[blue]W-[/]",
    "experiment_result": "[yellow]RES[/]",
    "round_started": "[magenta]RND+[/]",
    "round_completed": "[green]RND\u2713[/]",
    "session_started": "[bold cyan]START[/]",
    "loop_paused": "[yellow]PAUSE[/]",
    "frontier_complete": "[green]FRONTIER\u2713[/]",
}


class LogPanel(Vertical):
    """Append-only rich log display — incremental updates, no flicker."""

    def on_mount(self) -> None:
        self._seen_count = 0

    def compose(self):  # type: ignore[override]
        yield RichLog(id="log-view", highlight=True, markup=True, wrap=True)

    def update_data(self, events: list[dict[str, Any]]) -> None:
        n = len(events)
        # Handle log rotation / new session (count shrank)
        if n < self._seen_count:
            self._seen_count = 0
            self.query_one("#log-view", RichLog).clear()

        if n <= self._seen_count:
            return

        log: RichLog = self.query_one("#log-view", RichLog)
        new_events = events[self._seen_count:]
        for ev in new_events:
            ts = _ts_short(ev.get("ts", ""))
            etype = ev.get("event", ev.get("type", "info"))
            prefix = _EVENT_PREFIXES.get(etype, f"[dim]{etype}[/]")
            msg = ev.get("message", ev.get("msg", ev.get("line", "")))

            if etype == "skill_completed":
                rc = ev.get("exit_code", 0)
                step = ev.get("step", "")
                if rc == 0:
                    prefix = "[green]DONE\u2713[/]"
                    msg = msg or step
                else:
                    prefix = "[bold red]FAIL\u2717[/]"
                    msg = f"{step} (exit_code={rc})"

            elif etype == "session_ended":
                status = ev.get("status", "")
                if status == "completed":
                    prefix = "[bold green]SESSION\u2713[/]"
                    msg = "Research session completed"
                elif status == "crashed":
                    prefix = "[bold red]CRASH[/]"
                    msg = ev.get("error", "Runner exception")
                else:
                    prefix = "[bold red]SESSION\u2717[/]"
                    stage = ev.get("stage", "unknown")
                    rc = ev.get("exit_code", "?")
                    msg = f"Failed at {stage} (exit_code={rc})"

            elif not msg:
                msg = ev.get("step", ev.get("skill", ""))

            log.write(f"[dim]{ts}[/] {prefix} {msg}")
        self._seen_count = n


# ---------------------------------------------------------------------------
# MetricChart
# ---------------------------------------------------------------------------


class MetricChart(Static):
    """Simple text-based chart of kept result values using plotext."""

    def on_mount(self) -> None:
        self._last_count = -1

    def update_data(self, results: list[dict[str, Any]]) -> None:
        kept = [r for r in results if r.get("status") == "keep"]
        if len(kept) == self._last_count:
            return
        self._last_count = len(kept)

        if not kept:
            self.update("[dim]No kept results yet.[/]")
            return
        values: list[float] = []
        for r in kept:
            try:
                values.append(float(r["value"]))
            except (ValueError, KeyError, TypeError):
                continue
        if not values:
            self.update("[dim]No numeric results to plot.[/]")
            return
        try:
            import plotext as plt

            plt.clf()
            plt.plot(list(range(1, len(values) + 1)), values, marker="braille")
            plt.title("Metric Trend")
            plt.xlabel("Result #")
            plt.plotsize(60, 8)
            chart = plt.build()
            self.update(chart)
        except ImportError:
            lines = " ".join(f"{v:.4f}" for v in values)
            self.update(f"[dim]Values: {lines}[/]")
