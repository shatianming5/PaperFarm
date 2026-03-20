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
    """Metrics panel with summary stats, trend chart, and results table."""

    BORDER_TITLE = "Metrics"

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

        # Extract numeric values from kept results
        values: list[float] = []
        for r in kept:
            try:
                values.append(float(r["value"]))
            except (ValueError, KeyError, TypeError):
                continue

        # -- Summary line --
        if not values:
            summary_w.update("[dim]No kept results yet.[/]")
            chart_w.update("")
            table_w.clear()
            return

        best = max(values)
        worst = min(values)
        latest = values[-1]
        mean = sum(values) / len(values)
        if len(values) >= 2:
            trend = "\u2191" if values[-1] > values[-2] else "\u2193" if values[-1] < values[-2] else "\u2192"
        else:
            trend = "\u2192"

        summary_w.update(
            f" [dim]Kept:[/][bold]{len(kept)}[/] "
            f"[dim]Disc:[/]{len(discarded)} "
            f"[dim]\u2502[/] "
            f"[dim]Best:[/][bold cyan]{best:.4f}[/] "
            f"[dim]Mean:[/]{mean:.4f} "
            f"[dim]Latest:[/][bold]{latest:.4f}[/]{trend}"
        )

        # -- Chart --
        self._render_chart(chart_w, values)

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

    # Gradient styles for chart rows (top=bright, bottom=dim)
    _CHART_STYLES = [
        "bold bright_cyan",   # row near peak — brightest
        "bold cyan",
        "cyan",
        "dark_cyan",
    ]

    @staticmethod
    def _render_chart(widget: Static, values: list[float]) -> None:
        """Render a smooth braille area chart with gradient fill.

        Uses Unicode braille characters (U+2800-U+28FF) which provide
        2×4 pixel resolution per character cell, producing smooth curves
        with a gradient that fades from bright cyan at the line to dim
        blue at the bottom.
        """
        if not values:
            widget.update("")
            return

        vmin, vmax = min(values), max(values)
        vrange = vmax - vmin

        # Chart dimensions in character cells
        chart_cols = min(80, max(30, len(values) * 3))
        chart_rows = 10

        if vrange < 1e-9:
            # Flat data — show a mid-height horizontal band
            label = f"{vmin:.4f}"
            lines: list[str] = []
            mid = chart_rows // 2
            bar = chr(0x2800 | 0x01 | 0x02 | 0x08 | 0x10)  # ⠓ top two rows filled
            for crow in range(chart_rows):
                if crow == 0:
                    y_label = label
                elif crow == chart_rows - 1:
                    y_label = label
                else:
                    y_label = ""
                prefix = f"[dim]{y_label:>8} \u2502[/]"
                if crow == mid:
                    lines.append(f"{prefix}[bold cyan]{bar * chart_cols}[/]")
                elif crow == mid - 1 or crow == mid + 1:
                    fill = chr(0x2800 | 0x40 | 0x80) if crow == mid - 1 else chr(0x2800 | 0x01 | 0x08)
                    lines.append(f"{prefix}[dim cyan]{fill * chart_cols}[/]")
                else:
                    lines.append(f"{prefix}{chr(0x2800) * chart_cols}")
            lines.append(f"[dim]{' ' * 9}\u2514{'─' * chart_cols}[/]")
            widget.update("\n".join(lines))
            return

        # Pixel dimensions (braille: 2 dots wide × 4 dots tall per cell)
        px_w = chart_cols * 2
        px_h = chart_rows * 4

        # Braille dot positions within a cell:
        # Col 0: rows 0-3 → bits 0,1,2,6
        # Col 1: rows 0-3 → bits 3,4,5,7
        _DOT_MAP = [
            [0x01, 0x08],
            [0x02, 0x10],
            [0x04, 0x20],
            [0x40, 0x80],
        ]

        # Build pixel grid + track the line position per column
        grid = [[False] * px_w for _ in range(px_h)]
        line_y = [0] * px_w  # track line height for gradient coloring

        n = len(values)
        for px_x in range(px_w):
            # Map pixel x to data index (fractional)
            data_x = px_x / max(1, px_w - 1) * (n - 1)
            idx = int(data_x)
            frac = data_x - idx
            if idx >= n - 1:
                v = values[-1]
            else:
                v = values[idx] * (1 - frac) + values[idx + 1] * frac

            # Map value to pixel y (0 = bottom, px_h-1 = top)
            py = int((v - vmin) / vrange * (px_h - 1) + 0.5)
            py = max(0, min(px_h - 1, py))
            line_y[px_x] = py

            # Fill area: from bottom (0) to the line point
            for y in range(py + 1):
                grid[y][px_x] = True

            # Thicken the line slightly (1 extra pixel above)
            if py + 1 < px_h:
                grid[py + 1][px_x] = True

        # Convert grid to braille characters with gradient coloring
        # Grid y=0 is bottom; chart row 0 renders the TOP of the chart
        y_labels = {0: vmax, chart_rows // 2: (vmin + vmax) / 2, chart_rows - 1: vmin}
        styles = MetricChart._CHART_STYLES

        lines = []
        for crow in range(chart_rows):
            # Y-axis label
            if crow in y_labels:
                label = f"{y_labels[crow]:.4f}"
            else:
                label = ""
            parts = [f"[dim]{label:>8} \u2502[/]"]

            # Build braille characters for this row
            row_chars: list[str] = []
            row_has_dots = False
            for ccol in range(chart_cols):
                code = 0x2800
                for dy in range(4):
                    for dx in range(2):
                        gy = px_h - 1 - (crow * 4 + dy)
                        gx = ccol * 2 + dx
                        if 0 <= gy < px_h and 0 <= gx < px_w and grid[gy][gx]:
                            code |= _DOT_MAP[dy][dx]
                row_chars.append(chr(code))
                if code != 0x2800:
                    row_has_dots = True

            braille_str = "".join(row_chars)
            if not row_has_dots:
                parts.append(braille_str)
            else:
                # Determine gradient color based on row position relative to data
                # Find the average line height in character rows
                avg_line_crow = chart_rows - 1 - (sum(line_y) / len(line_y)) / 4
                dist = crow - avg_line_crow  # positive = below line
                if dist <= 0:
                    style = styles[0]  # at or above line: brightest
                elif dist < len(styles):
                    style = styles[int(dist)]
                else:
                    style = styles[-1]  # deep fill: dimmest
                parts.append(f"[{style}]{braille_str}[/]")

            lines.append("".join(parts))

        # X-axis line
        lines.append(f"[dim]{' ' * 9}\u2514{'─' * chart_cols}[/]")

        # X-axis labels (evenly spaced)
        num_labels = min(n, max(3, chart_cols // 8))
        label_data_idxs: list[int] = []
        for i in range(num_labels):
            label_data_idxs.append(round(i / max(1, num_labels - 1) * (n - 1)))

        # Map data indices to chart columns
        label_slots: list[tuple[int, str]] = []
        for di in label_data_idxs:
            col = round(di / max(1, n - 1) * (chart_cols - 1)) if n > 1 else 0
            label_slots.append((col, str(di + 1)))

        # Render x-axis avoiding overlaps
        x_line = [" "] * (chart_cols + 5)
        for col, text in label_slots:
            start = col
            if start + len(text) <= len(x_line):
                # Check for overlap
                if all(x_line[start + j] == " " for j in range(len(text))):
                    for j, ch in enumerate(text):
                        x_line[start + j] = ch
        lines.append(f"[dim]{' ' * 9}{''.join(x_line).rstrip()}[/]")

        widget.update("\n".join(lines))
