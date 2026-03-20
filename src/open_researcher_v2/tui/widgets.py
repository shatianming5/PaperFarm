"""TUI widgets for the Open-Researcher v2 command center.

Each widget exposes an ``update_data`` (or ``update_phase``) method that
accepts plain dicts/lists produced by ``ResearchState.summary()``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from textual.containers import Vertical
from textual.widgets import DataTable, RichLog, Static
from rich.text import Text

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PHASES = ("scout", "manager", "critic", "experiment")


def _ts_short(iso: str) -> str:
    """Convert an ISO timestamp to a compact ``HH:MM:SS`` string."""
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

    _PHASE_COLORS: dict[str, str] = {
        "idle": "dim",
        "scout": "cyan",
        "manager": "green",
        "critic": "yellow",
        "experiment": "magenta",
        "completed": "bold green",
        "failed": "bold red",
        "crashed": "bold red",
    }

    def update_data(self, summary: dict[str, Any]) -> None:
        phase = summary.get("phase", "idle")
        rnd = summary.get("round", 0)
        hyps = summary.get("hypotheses", 0)
        done = summary.get("experiments_done", 0)
        total = summary.get("experiments_total", 0)
        running = summary.get("experiments_running", 0)
        best = summary.get("best_value", "\u2014")
        pc = self._PHASE_COLORS.get(phase, "white")
        suffix = ""
        if summary.get("paused"):
            suffix = "  [bold yellow]\u23f8 PAUSED[/]"
        review = summary.get("awaiting_review")
        if review:
            rtype = review.get("type", "").replace("_", " ").upper()
            suffix = f"  [bold yellow]\u23f3 REVIEW {rtype}[/]"
        self.update(
            f"[dim]Phase:[/] [{pc}]{phase}[/] [dim]|[/] "
            f"[dim]Round:[/] [bold]{rnd}[/] [dim]|[/] "
            f"[dim]Hyps:[/] [bold]{hyps}[/] [dim]|[/] "
            f"[dim]Exps:[/] [bold]{done}/{total}[/] ({running}) [dim]|[/] "
            f"[dim]Best:[/] [bold cyan]{best}[/]{suffix}"
        )


# ---------------------------------------------------------------------------
# PhaseStripBar
# ---------------------------------------------------------------------------


class PhaseStripBar(Static):
    """Horizontal phase indicator highlighting the active phase in green."""

    def update_phase(self, phase: str) -> None:
        parts: list[str] = []
        passed = True
        for p in _PHASES:
            if p == phase:
                parts.append(f"[bold green]\u25b6 {p.upper()}[/]")
                passed = False
            elif phase == "completed":
                # All phases completed
                parts.append(f"[green]\u2713 {p}[/]")
            elif passed and phase not in ("idle", "failed", "crashed"):
                parts.append(f"[green]\u2713 {p}[/]")
            else:
                parts.append(f"[dim]{p}[/]")
        if phase in ("failed", "crashed"):
            parts.append(f"[bold red]\u2717 {phase.upper()}[/]")
        elif phase == "completed":
            parts.append(f"[bold green]\u2713 DONE[/]")
        self.update("  \u2023  ".join(parts))


# ---------------------------------------------------------------------------
# FrontierPanel
# ---------------------------------------------------------------------------


_STATUS_STYLES: dict[str, str] = {
    "approved": "green",
    "running": "cyan",
    "needs_post_review": "yellow",
    "needs_review": "yellow",
    "completed": "bold green",
    "keep": "bold green",
    "discard": "dim",
    "rejected": "dim red",
    "error": "bold red",
    "crash": "bold red",
    "draft": "dim",
}


class FrontierPanel(Vertical):
    """DataTable listing frontier items sorted by priority."""

    BORDER_TITLE = "Frontier"

    def compose(self):  # type: ignore[override]
        table = DataTable(id="frontier-table")
        table.add_columns("ID", "Pri", "Status", "Description")
        yield table

    @staticmethod
    def _safe_priority(item: dict) -> float:
        try:
            return float(item.get("priority", 0))
        except (ValueError, TypeError):
            return 0.0

    def update_data(self, frontier: list[dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#frontier-table", DataTable)
        table.clear()
        items = sorted(frontier, key=lambda f: -self._safe_priority(f))
        for item in items:
            status = str(item.get("status", ""))
            style = _STATUS_STYLES.get(status, "white")
            table.add_row(
                str(item.get("id", "")),
                str(item.get("priority", "")),
                Text(status, style=style),
                str(item.get("description", ""))[:60],
            )


# ---------------------------------------------------------------------------
# WorkerPanel
# ---------------------------------------------------------------------------


class WorkerPanel(Vertical):
    """DataTable showing live worker status."""

    BORDER_TITLE = "Workers"

    def compose(self):  # type: ignore[override]
        table = DataTable(id="worker-table")
        table.add_columns("Worker", "Status", "GPU", "Frontier")
        yield table

    def update_data(self, workers: list[dict[str, Any]]) -> None:
        table: DataTable = self.query_one("#worker-table", DataTable)
        table.clear()
        for w in workers:
            status = str(w.get("status", ""))
            style = _STATUS_STYLES.get(status, "white")
            table.add_row(
                str(w.get("id", "")),
                Text(status, style=style),
                str(w.get("gpu", "")),
                str(w.get("frontier_id", "")),
            )


# ---------------------------------------------------------------------------
# LogPanel
# ---------------------------------------------------------------------------

_EVENT_PREFIXES: dict[str, str] = {
    "skill_started": "[cyan]SKILL[/]",
    "skill_completed": "[green]DONE [/]",
    "output": "[white]OUT  [/]",
    "worker_started": "[blue]W+   [/]",
    "worker_finished": "[blue]W-   [/]",
    "experiment_result": "[yellow]RES  [/]",
    "review_requested": "[bold yellow]WAIT [/]",
    "review_completed": "[green]REVW [/]",
    "review_timeout": "[yellow]TOUT [/]",
    "review_skipped": "[dim]SKIP [/]",
    "human_injected": "[bold cyan]INJ  [/]",
    "human_override": "[bold magenta]OVRD [/]",
    "goal_updated": "[cyan]GOAL [/]",
}


class LogPanel(Vertical):
    """Append-only rich log display."""

    BORDER_TITLE = "Logs"

    def compose(self):  # type: ignore[override]
        yield RichLog(id="log-view", highlight=True, markup=True, wrap=True)

    def update_data(self, events: list[dict[str, Any]]) -> None:
        log: RichLog = self.query_one("#log-view", RichLog)
        log.clear()
        for ev in events:
            ts = _ts_short(ev.get("ts", ""))
            etype = ev.get("event", ev.get("type", "info"))
            prefix = _EVENT_PREFIXES.get(etype, f"[dim]{etype}[/]")
            msg = ev.get("message", ev.get("msg", ev.get("line", "")))
            log.write(f"[dim]{ts}[/] {prefix} [dim]│[/] {msg}")


# ---------------------------------------------------------------------------
# MetricChart
# ---------------------------------------------------------------------------


class MetricChart(Vertical):
    """Metrics panel with per-metric sparkline line charts and results table."""

    BORDER_TITLE = "Metrics"

    _COLORS = ["cyan", "green", "yellow", "magenta", "blue"]

    # Braille dot positions within a cell (row, col) → bit
    _DOT_MAP = [
        [0x01, 0x08],
        [0x02, 0x10],
        [0x04, 0x20],
        [0x40, 0x80],
    ]

    def compose(self):  # type: ignore[override]
        yield Static(id="metric-summary")
        yield Static(id="metric-chart")
        table = DataTable(id="metric-results")
        table.add_columns("#", "Frontier", "Status", "Metric", "Value", "Worker", "Desc")
        yield table

    def update_data(self, results: list[dict[str, Any]]) -> None:
        summary_w: Static = self.query_one("#metric-summary", Static)
        chart_w: Static = self.query_one("#metric-chart", Static)
        table_w: DataTable = self.query_one("#metric-results", DataTable)

        kept = [r for r in results if r.get("status") == "keep"]
        discarded = [r for r in results if r.get("status") == "discard"]

        # Group kept results by metric name (preserve insertion order)
        metric_data: dict[str, list[float]] = {}
        for r in kept:
            metric = r.get("metric", "") or "value"
            try:
                v = float(r["value"])
            except (ValueError, KeyError, TypeError):
                continue
            metric_data.setdefault(metric, []).append(v)

        if not metric_data:
            summary_w.update("[dim]No kept results yet.[/]")
            chart_w.update("")
            table_w.clear()
            return

        # -- Summary line --
        n_metrics = len(metric_data)
        if n_metrics == 1:
            name, vals = next(iter(metric_data.items()))
            best = max(vals)
            latest = vals[-1]
            mean = sum(vals) / len(vals)
            trend = self._trend_arrow(vals)
            summary_w.update(
                f" [dim]Kept: [/][bold]{len(kept)} [/]"
                f"[dim]Disc: [/]{len(discarded)} "
                f"[dim]\u2502 [/]"
                f"[dim]Best: [/][bold cyan]{best:.4f} [/]"
                f"[dim]Mean: [/]{mean:.4f} "
                f"[dim]Latest: [/][bold]{latest:.4f}[/]{trend}"
            )
        else:
            summary_w.update(
                f" [dim]Kept: [/][bold]{len(kept)} [/]"
                f"[dim]Disc: [/]{len(discarded)} "
                f"[dim]\u2502 [/]"
                f"[dim]{n_metrics} metrics tracked[/]"
            )

        # -- Sparkline charts --
        self._render_sparklines(chart_w, metric_data)

        # -- Results table (most recent first, up to 20 rows) --
        table_w.clear()
        recent = list(reversed(results[-20:]))
        for i, r in enumerate(recent):
            idx = len(results) - i
            status = str(r.get("status", ""))
            style = _STATUS_STYLES.get(status, "white")
            table_w.add_row(
                str(idx),
                str(r.get("frontier_id", "")),
                Text(status, style=style),
                str(r.get("metric", "")),
                str(r.get("value", "")),
                str(r.get("worker", "")),
                str(r.get("description", ""))[:40],
            )

    @staticmethod
    def _trend_arrow(vals: list[float]) -> str:
        if len(vals) < 2:
            return "\u2192"
        return "\u2191" if vals[-1] > vals[-2] else "\u2193" if vals[-1] < vals[-2] else "\u2192"

    def _render_sparklines(self, widget: Static, metric_data: dict[str, list[float]]) -> None:
        """Render stacked sparkline line charts, one per metric."""
        n_metrics = len(metric_data)
        max_n = max(len(vs) for vs in metric_data.values())
        chart_cols = min(80, max(20, max_n * 2))

        # Allocate chart rows per metric
        if n_metrics == 1:
            rows_per = 8
        elif n_metrics == 2:
            rows_per = 5
        elif n_metrics <= 4:
            rows_per = 4
        else:
            rows_per = 3

        colors = self._COLORS
        lines: list[str] = []

        for i, (name, values) in enumerate(metric_data.items()):
            color = colors[i % len(colors)]
            best = max(values)
            latest = values[-1]
            mean = sum(values) / len(values)
            trend = self._trend_arrow(values)

            # Metric header — trailing spaces INSIDE [/] to avoid Textual eating them
            lines.append(
                f" [{color}]\u25cf {name}  [/]"
                f"best: [{color} bold]{best:.4f}  [/]"
                f"latest: [bold]{latest:.4f}[/]{trend}"
                f"  [dim]mean: {mean:.4f}  n={len(values)}[/]"
            )

            if len(values) < 2:
                lines.append(f"   [dim]Single point: {values[0]:.4f}[/]")
            else:
                chart_lines = self._render_line(values, chart_cols, rows_per, color)
                lines.extend(chart_lines)

            # Separator between metrics
            if i < n_metrics - 1:
                lines.append("")

        widget.update("\n".join(lines))

    @classmethod
    def _render_line(cls, values: list[float], chart_cols: int,
                     chart_rows: int, color: str) -> list[str]:
        """Render a single braille line chart (line only, no area fill)."""
        vmin, vmax = min(values), max(values)
        vrange = vmax - vmin

        # Add 5% padding so line doesn't touch edges
        if vrange < 1e-9:
            vrange = max(abs(vmin) * 0.1, 0.01)
            vmin -= vrange / 2
            vmax += vrange / 2
            vrange = vmax - vmin
        else:
            pad = vrange * 0.05
            vmin -= pad
            vmax += pad
            vrange = vmax - vmin

        px_w = chart_cols * 2
        px_h = chart_rows * 4
        grid = [[False] * px_w for _ in range(px_h)]

        n = len(values)
        prev_py: int | None = None

        for px_x in range(px_w):
            # Interpolate data value
            data_x = px_x / max(1, px_w - 1) * (n - 1)
            idx = int(data_x)
            frac = data_x - idx
            if idx >= n - 1:
                v = values[-1]
            else:
                v = values[idx] * (1 - frac) + values[idx + 1] * frac

            # Map to pixel Y (0 = bottom, px_h-1 = top)
            py = int((v - vmin) / vrange * (px_h - 1) + 0.5)
            py = max(0, min(px_h - 1, py))

            # Draw line point
            grid[py][px_x] = True

            # Connect to previous point to avoid gaps
            if prev_py is not None and abs(py - prev_py) > 1:
                lo, hi = min(prev_py, py), max(prev_py, py)
                for y in range(lo, hi + 1):
                    grid[y][px_x] = True

            prev_py = py

        # Thicken line by 1 pixel upward for visibility
        for px_x in range(px_w):
            for py in range(px_h - 2, -1, -1):
                if grid[py][px_x] and py + 1 < px_h:
                    grid[py + 1][px_x] = True

        # Convert grid to braille characters
        y_labels = {0: vmax, chart_rows - 1: vmin}
        dot_map = cls._DOT_MAP

        lines: list[str] = []
        for crow in range(chart_rows):
            label = f"{y_labels[crow]:.4f}" if crow in y_labels else ""
            axis_ch = "\u2524" if crow in y_labels else "\u2502"

            row_chars: list[str] = []
            has_dots = False
            for ccol in range(chart_cols):
                code = 0x2800
                for dy in range(4):
                    for dx in range(2):
                        gy = px_h - 1 - (crow * 4 + dy)
                        gx = ccol * 2 + dx
                        if 0 <= gy < px_h and 0 <= gx < px_w and grid[gy][gx]:
                            code |= dot_map[dy][dx]
                row_chars.append(chr(code))
                if code != 0x2800:
                    has_dots = True

            braille = "".join(row_chars)
            prefix = f"[dim]{label:>8}{axis_ch}[/]"
            if has_dots:
                lines.append(f"{prefix}[{color}]{braille}[/]")
            else:
                lines.append(f"{prefix}{braille}")

        # X-axis
        lines.append(f"[dim]{' ' * 8}\u2514{'─' * chart_cols}[/]")

        # X-axis labels
        num_labels = min(n, max(3, chart_cols // 8))
        x_line = [" "] * (chart_cols + 5)
        for i in range(num_labels):
            di = round(i / max(1, num_labels - 1) * (n - 1))
            col = round(di / max(1, n - 1) * (chart_cols - 1)) if n > 1 else 0
            text = str(di + 1)
            if col + len(text) <= len(x_line):
                if all(x_line[col + j] == " " for j in range(len(text))):
                    for j, ch in enumerate(text):
                        x_line[col + j] = ch
        lines.append(f"[dim]{' ' * 9}{''.join(x_line).rstrip()}[/]")

        return lines
