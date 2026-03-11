"""Custom Textual widgets for Open Researcher TUI — Rich-colored rendering."""

from __future__ import annotations

import logging

from rich.markup import escape
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

logger = logging.getLogger(__name__)

# Theme colors for Rich markup
C_SUCCESS = "#73daca"
C_ERROR = "#f7768e"
C_WARNING = "#e0af68"
C_INFO = "#7dcfff"
C_PRIMARY = "#7aa2f7"
C_SECONDARY = "#9ece6a"
C_ACCENT = "#bb9af7"
C_TEXT = "#c0caf5"
C_BEST = "#2ac3de"
C_DIM = "#565f89"


class StatsBar(Static):
    """Top status bar showing experiment summary with Rich color markup."""

    stats_text = reactive("")

    def render(self) -> str:
        return self.stats_text or "Open Researcher — starting..."

    def update_stats(self, state: dict, phase: str = "", paused: bool = False) -> None:
        total = state.get("total", 0)
        keep = state.get("keep", 0)
        discard = state.get("discard", 0)
        crash = state.get("crash", 0)
        best = state.get("best_value")
        pm = state.get("primary_metric", "")

        parts: list[str] = []
        # Phase badge
        _phase_badges = {
            "scouting": f"[bold {C_TEXT} on {C_PRIMARY}] SCOUT [/]",
            "reviewing": f"[bold {C_TEXT} on {C_WARNING}] REVIEW [/]",
            "experimenting": f"[bold {C_TEXT} on {C_SUCCESS}] EXPERIMENT [/]",
        }
        if phase in _phase_badges:
            parts.append(_phase_badges[phase])
        parts.append("[bold]Open Researcher[/bold]")
        if paused:
            parts.append(f"[bold {C_ERROR}]PAUSED[/bold {C_ERROR}]")
        if total > 0:
            parts.append(f"[{C_SUCCESS}]{keep}K[/{C_SUCCESS}] [{C_ERROR}]{discard}D[/{C_ERROR}]")
            if crash:
                parts.append(f"[{C_WARNING}]{crash}C[/{C_WARNING}]")
            if best is not None:
                try:
                    best_str = f"{float(best):.4f}"
                except (ValueError, TypeError):
                    best_str = str(best)
                parts.append(f"[bold {C_BEST}]best={best_str}[/bold {C_BEST}]")
        else:
            parts.append("[dim]waiting...[/dim]")

        self.stats_text = " | ".join(parts)


class ExperimentStatusPanel(Static):
    """Prominent display of experiment agent phase with colored icons."""

    status_text = reactive("", layout=True)

    def render(self) -> str:
        return self.status_text or "[dim]-- \\[IDLE] waiting to start...[/dim]"

    def update_status(
        self, activity: dict | None, completed: int = 0, total: int = 0,
        phase: str = "",
        role_label: str = "Experiment Agent",
    ) -> None:
        # Phase-specific rendering for scouting and reviewing
        if phase == "scouting":
            detail = escape((activity or {}).get("detail", "Analyzing project..."))
            self.status_text = (
                f"  [bold {C_PRIMARY}]Scout Agent[/bold {C_PRIMARY}]\n"
                f"     [{C_DIM}]{detail}[/{C_DIM}]"
            )
            return
        if phase == "reviewing":
            self.status_text = (
                f"  [bold {C_WARNING}]Review[/bold {C_WARNING}]\n"
                f"     [{C_DIM}]Waiting for user confirmation[/{C_DIM}]"
            )
            return

        if not activity:
            self.status_text = "[dim]-- \\[IDLE] waiting to start...[/dim]"
            return

        status = activity.get("status", "idle")
        detail = escape(activity.get("detail", ""))
        frontier = escape(activity.get("frontier_id", "") or activity.get("idea", ""))

        # Phase icon and color mapping
        phase_map: dict[str, tuple[str, str, str]] = {
            "running": ("\u25b6", C_SUCCESS, "RUNNING"),
            "establishing_baseline": ("\u27f3", C_WARNING, "BASELINE"),
            "paused": ("\u23f8", C_WARNING, "PAUSED"),
            "idle": ("--", C_DIM, "IDLE"),
            "analyzing": ("\u25b6", C_INFO, "ANALYZING"),
            "generating": ("**", C_ACCENT, "GENERATING"),
            "searching": ("..", C_PRIMARY, "SEARCHING"),
            "coding": ("<>", C_SUCCESS, "CODING"),
            "evaluating": ("##", C_INFO, "EVALUATING"),
            "scheduling": ("::", C_WARNING, "SCHEDULING"),
            "detecting_gpus": ("||", C_PRIMARY, "DETECTING_GPUS"),
            "monitoring": ("()", C_INFO, "MONITORING"),
            "cpu_serial_mode": ("\\[]", C_WARNING, "CPU_SERIAL"),
        }

        icon, color, label = phase_map.get(status, ("*", C_TEXT, status.upper()))

        lines: list[str] = []
        if phase == "experimenting":
            lines.append(f"  [bold {C_SUCCESS}]{escape(role_label)}[/bold {C_SUCCESS}]")
        lines.append(f"  [{color}]{icon} \\[{label}][/{color}]")
        if frontier:
            lines.append(f"     [bold]{frontier}[/bold]")
        if detail:
            lines.append(f"     [dim]{detail}[/dim]")

        # Progress bar
        if total > 0:
            bar_width = 20
            filled = min(int(bar_width * completed / total), bar_width) if total else 0
            empty = bar_width - filled
            bar = "\u2588" * filled + "\u2591" * empty
            lines.append(f"     [{color}]{bar}[/{color}]  {completed}/{total} backlog items")

        self.status_text = "\n".join(lines)


class ProjectedBacklogPanel(Static):
    """Rich-formatted projected backlog list."""

    items_text = reactive("", layout=True)

    def render(self) -> str:
        return self.items_text or "[dim]No projected backlog items yet[/dim]"

    def update_items(self, ideas: list[dict]) -> None:
        if not ideas:
            self.items_text = "[dim]No projected backlog items yet[/dim]"
            return

        def _sort_key(i):
            return (
                int(i.get("priority", 9999) or 9999),
                str(i.get("id", "")),
            )
        sorted_ideas = sorted(ideas, key=_sort_key)

        lines: list[str] = []
        for idea in sorted_ideas:
            sid = idea.get("status", "pending")
            result = idea.get("result")
            verdict = ""
            if result and isinstance(result, dict):
                verdict = result.get("verdict", "")

            desc = escape(idea.get("description", ""))
            if len(desc) > 50:
                desc = desc[:47] + "..."
            item_label = escape(idea.get("frontier_id", "") or idea.get("id", "item"))

            if sid == "running":
                icon = f"[bold {C_WARNING}]\u25b6[/bold {C_WARNING}]"
                result_str = f"[bold {C_WARNING}]running...[/bold {C_WARNING}]"
            elif sid == "pending":
                icon = f"[{C_DIM}]\u00b7[/{C_DIM}]"
                result_str = f"[{C_DIM}]pending[/{C_DIM}]"
            elif verdict == "kept" or (sid == "done" and verdict != "discarded"):
                icon = f"[{C_SUCCESS}]\u2713[/{C_SUCCESS}]"
                val = ""
                if result and isinstance(result, dict):
                    raw_val = result.get("metric_value")
                    if raw_val is not None:
                        try:
                            val = f" val={float(raw_val):.4f}"
                        except (ValueError, TypeError):
                            val = f" val={raw_val}"
                result_str = f"[{C_SUCCESS}]kept{val}[/{C_SUCCESS}]"
            elif verdict == "discarded":
                icon = f"[{C_ERROR}]\u2717[/{C_ERROR}]"
                val = ""
                if result and isinstance(result, dict):
                    raw_val = result.get("metric_value")
                    if raw_val is not None:
                        try:
                            val = f" val={float(raw_val):.4f}"
                        except (ValueError, TypeError):
                            val = f" val={raw_val}"
                result_str = f"[{C_ERROR}]disc{val}[/{C_ERROR}]"
            elif sid == "skipped":
                icon = "[dim]\u2013[/dim]"
                result_str = "[dim]skipped[/dim]"
            else:
                icon = "[dim]?[/dim]"
                result_str = f"[dim]{sid}[/dim]"

            line = f"  {icon} [bold]{item_label}[/bold] | {desc}  \u2192 {result_str}"
            lines.append(line)

        self.items_text = "\n".join(lines)

    def update_ideas(self, ideas: list[dict]) -> None:
        self.update_items(ideas)


class IdeaListPanel(ProjectedBacklogPanel):
    """Backward-compatible alias for tests/imports."""

    @property
    def ideas_text(self) -> str:
        return self.items_text


class HotkeyBar(Static):
    """Bottom bar showing available keyboard shortcuts with Rich styling."""

    bar_text: reactive[str] = reactive("")

    def render(self) -> str:
        return self.bar_text or self._build_keys()

    def update_state(self, paused: bool = False, phase: str = "") -> None:
        self.bar_text = self._build_keys(paused=paused, phase=phase)

    @staticmethod
    def _build_keys(paused: bool = False, phase: str = "") -> str:
        keys = [
            f"[bold {C_INFO}]\\[1][/bold {C_INFO}][{C_DIM}]-[/{C_DIM}][bold {C_INFO}]\\[5][/bold {C_INFO}][{C_DIM}]tabs[/{C_DIM}]",
        ]
        if paused:
            keys.append(f"[bold {C_SUCCESS}]\\[r][/bold {C_SUCCESS}][bold]esume[/bold]")
        else:
            keys.append(f"[bold {C_INFO}]\\[p][/bold {C_INFO}][{C_DIM}]ause[/{C_DIM}]")
        if phase == "experimenting":
            keys.append(f"[bold {C_INFO}]\\[s][/bold {C_INFO}][{C_DIM}]kip item[/{C_DIM}]")
        keys.append(f"[bold {C_INFO}]\\[g][/bold {C_INFO}][{C_DIM}]pu[/{C_DIM}]")
        keys.append(f"[bold {C_INFO}]\\[q][/bold {C_INFO}][{C_DIM}]uit[/{C_DIM}]")
        if paused:
            keys.append(f"[bold {C_ERROR}]PAUSED[/bold {C_ERROR}]")
        return " ".join(keys)


class MetricChart(Static):
    """Experiment metric trend chart using plotext (via textual-plotext)."""

    def compose(self) -> ComposeResult:
        from textual_plotext import PlotextPlot

        yield PlotextPlot(id="plotext-inner")

    def on_mount(self) -> None:
        try:
            from textual_plotext import PlotextPlot

            plot_widget = self.query_one("#plotext-inner", PlotextPlot)
            plot_widget.plt.title("Metric Trend")
            plot_widget.refresh()
        except Exception:
            logger.debug("Error initializing metric chart", exc_info=True)

    def update_data(self, rows: list[dict], metric_name: str = "metric") -> None:
        """Update chart with experiment results."""
        try:
            from textual_plotext import PlotextPlot

            plot_widget = self.query_one("#plotext-inner", PlotextPlot)
        except Exception:
            return

        p = plot_widget.plt
        p.clear_figure()

        if not rows:
            p.title("No experiment data yet")
            plot_widget.refresh()
            return

        values = []
        statuses = []
        indices = []
        for idx, r in enumerate(rows, 1):
            try:
                val = float(r.get("metric_value", 0))
            except (ValueError, TypeError):
                continue  # skip invalid values instead of filling 0
            values.append(val)
            statuses.append(r.get("status", ""))
            indices.append(idx)

        if not values:
            p.title("No valid metric data")
            plot_widget.refresh()
            return

        p.plot(indices, values, marker="braille")

        # Colored scatter by status
        for status, color in [("keep", "green"), ("discard", "red"), ("crash", "yellow")]:
            sx = [indices[i] for i, s in enumerate(statuses) if s == status]
            sy = [values[i] for i, s in enumerate(statuses) if s == status]
            if sx:
                p.scatter(sx, sy, color=color)

        # Reference lines
        if values:
            p.hline(values[0], color="blue")  # baseline

        p.title(f"{metric_name} Trend")
        p.xlabel("Experiment #")
        p.ylabel(metric_name)
        plot_widget.refresh()


class RecentExperiments(Static):
    """Shows the last few experiment results with colored status."""

    results_text = reactive("", layout=True)

    def render(self) -> str:
        return self.results_text or "[dim]No experiments yet[/dim]"

    def update_results(self, rows: list[dict]) -> None:
        if not rows:
            self.results_text = "[dim]No experiments yet[/dim]"
            return

        lines = ["[bold]Recent Experiments:[/bold]"]
        status_style = {"keep": C_SUCCESS, "discard": C_ERROR, "crash": C_WARNING}
        status_icon = {"keep": "\u2713", "discard": "\u2717", "crash": "\u2620"}

        for i, r in enumerate(rows[-5:], 1):
            st = r.get("status", "?")
            desc = escape(r.get("description", ""))[:40]
            raw_val = r.get("metric_value", "?")
            try:
                val_str = f"{float(raw_val):>8.4f}"
            except (ValueError, TypeError):
                val_str = f"{str(raw_val):>8s}"
            color = status_style.get(st, C_DIM)
            icon = status_icon.get(st, "?")
            lines.append(f"  [{color}]{icon} {val_str}  {desc}[/{color}]")

        self.results_text = "\n".join(lines)


def render_ideas_markdown(ideas: list[dict]) -> str:
    """Render the projected backlog as Markdown."""
    if not ideas:
        return "# Projected Backlog\n\n*No projected backlog items yet.*\n"

    def _sort_key(i):
        return (
            int(i.get("priority", 9999) or 9999),
            str(i.get("id", "")),
        )

    lines = [
        "# Projected Backlog",
        "",
        "| Item | Frontier | Description | Category | Priority | Status | Result |",
        "|------|----------|-------------|----------|----------|--------|--------|",
    ]

    counts: dict[str, int] = {}
    for idea in sorted(ideas, key=_sort_key):
        status = idea.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1

        num = idea.get("id", "?")
        frontier = idea.get("frontier_id", "").replace("|", "\\|")
        desc = idea.get("description", "").replace("|", "\\|")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        cat = idea.get("category", "").replace("|", "\\|")
        pri = str(idea.get("priority", ""))
        result = idea.get("result")
        if status == "running":
            result_str = "running..."
        elif result and isinstance(result, dict):
            verdict = result.get("verdict", "")
            raw_val = result.get("metric_value")
            if raw_val is not None:
                try:
                    result_str = f"{verdict} ({float(raw_val):.4f})"
                except (ValueError, TypeError):
                    result_str = f"{verdict} ({raw_val})"
            else:
                result_str = verdict
        else:
            result_str = ""
        result_str = result_str.replace("|", "\\|")

        item_label = num.replace("|", "\\|")
        lines.append(f"| {item_label} | {frontier} | {desc} | {cat} | {pri} | {status} | {result_str} |")

    parts = [f"{counts.get(s, 0)} {s}" for s in ("pending", "running", "done", "skipped") if counts.get(s)]
    lines.append(f"\n**Summary**: {', '.join(parts)}, {len(ideas)} total projected backlog items")
    return "\n".join(lines)


class DocViewer(Static):
    """Document viewer for .research/ markdown files with auto-refresh."""

    DEFAULT_CSS = """
    DocViewer {
        height: 1fr;
    }
    DocViewer #doc-content {
        height: 1fr;
        overflow-y: auto;
    }
    """

    DOC_FILES = [
        "project-understanding.md",
        "literature.md",
        "evaluation.md",
        "research-strategy.md",
        "manager_program.md",
        "critic_program.md",
        "experiment_program.md",
        "projected_backlog.md",
        "research_graph.md",
        "research_memory.md",
    ]

    DYNAMIC_FILES = {"projected_backlog.md", "research_graph.md", "research_memory.md"}

    def __init__(self, research_dir=None, **kwargs):
        super().__init__(**kwargs)
        self.research_dir = research_dir
        self._current_file: str = self.DOC_FILES[0]
        self._last_mtime: float = 0.0
        self._last_content_hash: int = 0

    def compose(self) -> ComposeResult:
        from textual.widgets import Markdown as MarkdownWidget
        from textual.widgets import Select

        options = [(f, f) for f in self.DOC_FILES]
        yield Select(options, value=self.DOC_FILES[0], id="doc-select")
        yield MarkdownWidget("Select a document to view", id="doc-content")

    async def on_mount(self) -> None:
        await self._load_doc(self.DOC_FILES[0])
        self.set_interval(5.0, self._schedule_refresh)

    def _read_content(self, filename: str) -> str:
        """Read document content (thread-safe, no widget access)."""
        if not self.research_dir or not filename:
            return ""
        if filename in self.DYNAMIC_FILES:
            return self._read_dynamic(filename)
        try:
            path = self.research_dir / filename
            if path.exists():
                return path.read_text()
            return f"*File not found: {filename}*"
        except (UnicodeDecodeError, OSError):
            return f"*Error reading: {filename}*"

    def _read_dynamic(self, filename: str) -> str:
        """Generate dynamic content for special files."""
        if filename == "projected_backlog.md":
            try:
                from open_researcher.idea_pool import IdeaBacklog
                pool = IdeaBacklog(self.research_dir / "idea_pool.json")
                return render_ideas_markdown(pool.all_ideas())
            except Exception:
                logger.debug("Error reading projected backlog", exc_info=True)
                return "# Projected Backlog\n\n*Error loading projected backlog.*\n"
        if filename == "research_graph.md":
            return self._render_json_markdown(
                title="Research Graph",
                source_file="research_graph.json",
            )
        if filename == "research_memory.md":
            return self._render_json_markdown(
                title="Research Memory",
                source_file="research_memory.json",
            )
        return ""

    def _render_json_markdown(self, *, title: str, source_file: str) -> str:
        path = self.research_dir / source_file
        if not path.exists():
            return f"# {title}\n\n*File not found: {source_file}*\n"
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("Error reading %s", source_file, exc_info=True)
            return f"# {title}\n\n*Error loading {source_file}.*\n"

        if source_file == "research_graph.json":
            summary = [
                f"- hypotheses: {len(payload.get('hypotheses', []))}",
                f"- experiment_specs: {len(payload.get('experiment_specs', []))}",
                f"- frontier: {len(payload.get('frontier', []))}",
                f"- evidence: {len(payload.get('evidence', []))}",
                f"- claim_updates: {len(payload.get('claim_updates', []))}",
            ]
        else:
            summary = [
                f"- repo_type_priors: {len(payload.get('repo_type_priors', []))}",
                f"- ideation_memory: {len(payload.get('ideation_memory', []))}",
                f"- experiment_memory: {len(payload.get('experiment_memory', []))}",
            ]
        pretty = json.dumps(payload, indent=2, ensure_ascii=False)
        return f"# {title}\n\n" + "\n".join(summary) + f"\n\n```json\n{pretty}\n```\n"

    def _get_file_mtime(self, filename: str) -> float:
        """Get modification time for change detection."""
        if not self.research_dir:
            return 0.0
        if filename == "projected_backlog.md":
            pool_path = self.research_dir / "idea_pool.json"
        elif filename == "research_graph.md":
            pool_path = self.research_dir / "research_graph.json"
        elif filename == "research_memory.md":
            pool_path = self.research_dir / "research_memory.json"
        else:
            pool_path = self.research_dir / filename
        try:
            return pool_path.stat().st_mtime if pool_path.exists() else 0.0
        except OSError:
            return 0.0

    def _bg_check_refresh(self) -> None:
        """Background thread: check file changes and push update to main thread."""
        filename = self._current_file
        if not filename or not self.research_dir:
            return

        if filename in self.DYNAMIC_FILES:
            content = self._read_content(filename)
            content_hash = hash(content)
            if content_hash == self._last_content_hash:
                return
            self.call_from_thread(self._do_update_content, content, 0.0, content_hash)
        else:
            mtime = self._get_file_mtime(filename)
            if mtime == self._last_mtime:
                return
            content = self._read_content(filename)
            content_hash = hash(content)
            self.call_from_thread(self._do_update_content, content, mtime, content_hash)

    def _schedule_refresh(self) -> None:
        """Timer callback: spawn background worker for I/O check."""
        self.run_worker(self._bg_check_refresh, thread=True)

    async def _do_update_content(self, content: str, mtime: float, content_hash: int) -> None:
        """Main-thread callback: update cached state and Markdown widget."""
        self._last_mtime = mtime
        self._last_content_hash = content_hash
        try:
            from textual.widgets import Markdown as MarkdownWidget
            md_widget = self.query_one("#doc-content", MarkdownWidget)
            result = md_widget.update(content)
            if result is not None:
                await result
        except Exception:
            logger.debug("Error updating doc content", exc_info=True)

    async def _load_doc(self, filename: str) -> None:
        """Load a document file into the viewer."""
        self._current_file = filename
        self._last_mtime = 0.0
        self._last_content_hash = 0
        content = self._read_content(filename)
        self._last_content_hash = hash(content)
        self._last_mtime = self._get_file_mtime(filename)
        try:
            from textual.widgets import Markdown as MarkdownWidget
            md_widget = self.query_one("#doc-content", MarkdownWidget)
            result = md_widget.update(content)
            if result is not None:
                await result
        except Exception:
            logger.debug("Error updating doc content", exc_info=True)

    async def on_select_changed(self, event) -> None:
        if event.value:
            await self._load_doc(event.value)
