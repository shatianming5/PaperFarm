"""Main Textual application for Open Researcher."""

import json
import logging
import time
from pathlib import Path
from typing import Literal

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.theme import Theme
from textual.widgets import RichLog, TabbedContent, TabPane

from open_researcher.activity import ActivityMonitor
from open_researcher.control_plane import issue_control_command, read_control
from open_researcher.idea_pool import IdeaBacklog
from open_researcher.status_cmd import parse_research_state
from open_researcher.tui.modals import GPUStatusModal, LogScreen
from open_researcher.tui.widgets import (
    DocViewer,
    ExperimentStatusPanel,
    ProjectedBacklogPanel,
    HotkeyBar,
    MetricChart,
    RecentExperiments,
    StatsBar,
)

logger = logging.getLogger(__name__)


class ResearchApp(App):
    """Interactive TUI for monitoring and controlling Open Researcher agents."""

    CSS_PATH = "styles.css"

    BINDINGS = [
        ("1", "switch_tab('tab-overview')", "Overview"),
        ("2", "switch_tab('tab-backlog')", "Backlog"),
        ("3", "switch_tab('tab-charts')", "Charts"),
        ("4", "switch_tab('tab-logs')", "Logs"),
        ("5", "switch_tab('tab-docs')", "Docs"),
        ("p", "pause", "Pause"),
        ("r", "resume", "Resume"),
        ("s", "skip", "Skip item"),
        ("g", "gpu_status", "GPU status"),
        ("l", "view_log", "View log"),
        ("q", "quit_app", "Quit"),
    ]

    app_phase: reactive[str] = reactive("experimenting")

    def __init__(self, repo_path: Path, on_ready=None, initial_phase: str = "experimenting"):
        super().__init__()
        self.repo_path = repo_path
        self.research_dir = repo_path / ".research"
        self.pool = IdeaBacklog(self.research_dir / "idea_pool.json")
        self.activity = ActivityMonitor(self.research_dir)
        self._on_ready = on_ready
        self.app_phase = initial_phase  # "scouting" | "reviewing" | "experimenting"
        self._state_cache: dict | None = None
        self._state_cache_time: float = 0.0
        self._last_tab_phase: str = ""

    def compose(self) -> ComposeResult:
        yield StatsBar(id="stats-bar")
        with TabbedContent(id="tabs"):
            with TabPane("Overview", id="tab-overview"):
                yield ExperimentStatusPanel(id="exp-status")
                yield RecentExperiments(id="recent-exp")
            with TabPane("Backlog", id="tab-backlog"):
                with ScrollableContainer(id="backlog-scroll"):
                    yield ProjectedBacklogPanel(id="backlog-list")
            with TabPane("Charts", id="tab-charts"):
                yield MetricChart(id="metric-chart")
            with TabPane("Logs", id="tab-logs"):
                yield RichLog(id="agent-log", wrap=True, markup=True)
            with TabPane("Docs", id="tab-docs"):
                yield DocViewer(research_dir=self.research_dir, id="doc-viewer")
        yield HotkeyBar(id="hotkey-bar")

    def on_mount(self) -> None:
        self.register_theme(Theme(
            name="open-researcher-dark",
            primary="#7aa2f7", secondary="#9ece6a",
            foreground="#c0caf5", background="#1a1b26",
            surface="#1e2030", panel="#24283b",
            warning="#e0af68", error="#f7768e",
            success="#73daca", accent="#bb9af7", dark=True,
        ))
        self.theme = "open-researcher-dark"
        self.set_interval(1.0, self._refresh_data)
        # Start agent threads AFTER event loop is running
        # to avoid call_from_thread failures during startup
        if self._on_ready:
            self._on_ready()

    def watch_app_phase(self, old_phase: str, new_phase: str) -> None:
        """Immediately update phase-dependent UI when phase changes."""
        # Update Logs tab title
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            tab = tabs.get_tab("tab-logs")
            _title_map = {
                "scouting": "Logs (Scout)",
                "reviewing": "Logs (Review)",
                "experimenting": "Logs (Experiment)",
            }
            tab.label = _title_map.get(new_phase, "Logs")
        except Exception:
            logger.debug("Error updating tab label in watcher", exc_info=True)
        # Force immediate refresh of stats/status/hotkey
        self._refresh_data()

    def action_switch_tab(self, tab_id: str) -> None:
        try:
            self.query_one("#tabs", TabbedContent).active = tab_id
        except NoMatches:
            logger.debug("Tab %s not found", tab_id)

    def _refresh_data(self) -> None:
        """Timer callback: kick off background I/O worker."""
        if not self._running:
            return
        self.run_worker(self._bg_gather_data, thread=True, exclusive=True, group="refresh")

    def _bg_gather_data(self) -> None:
        """Background thread: gather all data via file I/O, then apply on UI thread."""
        paused = False
        try:
            ctrl = self._read_control()
            paused = bool(ctrl.get("paused", False))
        except Exception:
            logger.debug("Error reading control state", exc_info=True)

        now = time.monotonic()
        if now - self._state_cache_time > 5.0 or self._state_cache is None:
            try:
                self._state_cache = parse_research_state(self.repo_path)
                self._state_cache_time = now
            except Exception:
                logger.debug("Error parsing research state", exc_info=True)
        state = self._state_cache

        ideas: list[dict] = []
        try:
            ideas = self.pool.all_ideas()
        except Exception:
            logger.debug("Error reading idea pool", exc_info=True)

        exp_act = None
        manager_act = None
        critic_act = None
        try:
            exp_act = self.activity.get("experiment_agent")
            manager_act = self.activity.get("manager_agent") or self.activity.get("idea_agent")
            critic_act = self.activity.get("critic_agent")
        except Exception:
            logger.debug("Error reading activity", exc_info=True)

        rows: list[dict] = []
        try:
            from open_researcher.results_cmd import load_results
            rows = load_results(self.repo_path)
        except Exception:
            logger.debug("Error loading results", exc_info=True)

        try:
            self.call_from_thread(
                self._apply_refresh_data, paused, state, ideas, exp_act, manager_act, critic_act, rows,
            )
        except RuntimeError:
            pass  # App already closed

    def _apply_refresh_data(
        self,
        paused: bool,
        state: dict | None,
        ideas: list[dict],
        exp_act: dict | None,
        manager_act: dict | None,
        critic_act: dict | None,
        rows: list[dict],
    ) -> None:
        """UI thread: apply pre-fetched data to widgets (no I/O)."""
        try:
            if state is not None:
                self.query_one("#stats-bar", StatsBar).update_stats(
                    state, phase=self.app_phase, paused=paused,
                )
        except NoMatches:
            logger.debug("Error refreshing stats bar", exc_info=True)

        completed = 0
        total = len(ideas)
        try:
            self.query_one("#backlog-list", ProjectedBacklogPanel).update_items(ideas)
            completed = sum(1 for i in ideas if i.get("status") in ("done", "skipped"))
        except NoMatches:
            logger.debug("Error refreshing projected backlog", exc_info=True)

        try:
            active = None
            role_label = "Experiment Agent"
            if exp_act and exp_act.get("status") not in (None, "idle"):
                active = exp_act
                role_label = "Experiment Agent"
            elif manager_act and manager_act.get("status") not in (None, "idle"):
                active = manager_act
                role_label = "Research Manager"
            elif critic_act and critic_act.get("status") not in (None, "idle"):
                active = critic_act
                role_label = "Research Critic"
            self.query_one("#exp-status", ExperimentStatusPanel).update_status(
                active, completed, total, phase=self.app_phase,
                role_label=role_label,
            )
        except NoMatches:
            logger.debug("Error refreshing experiment status", exc_info=True)

        try:
            self.query_one("#recent-exp", RecentExperiments).update_results(rows)
        except NoMatches:
            logger.debug("Error updating recent experiments", exc_info=True)
        try:
            metric_name = state.get("primary_metric", "metric") if state else "metric"
            self.query_one("#metric-chart", MetricChart).update_data(rows, metric_name)
        except NoMatches:
            logger.debug("Error updating metric chart", exc_info=True)

        # Update Logs tab title only when phase changes
        if self.app_phase != self._last_tab_phase:
            self._last_tab_phase = self.app_phase
            try:
                tabs = self.query_one("#tabs", TabbedContent)
                tab = tabs.get_tab("tab-logs")
                _title_map = {
                    "scouting": "Logs (Scout)",
                    "reviewing": "Logs (Review)",
                    "experimenting": "Logs (Experiment)",
                }
                tab.label = _title_map.get(self.app_phase, "Logs")
            except Exception:
                logger.debug("Error updating tab label", exc_info=True)

        try:
            self.query_one("#hotkey-bar", HotkeyBar).update_state(
                paused=paused, phase=self.app_phase,
            )
        except NoMatches:
            logger.debug("Error updating hotkey bar", exc_info=True)

    def _read_control(self) -> dict:
        return read_control(self.research_dir / "control.json")

    def _write_control_command(
        self,
        command: Literal["pause", "resume", "skip_current", "clear_skip"],
        reason: str | None = None,
    ) -> None:
        issue_control_command(
            self.research_dir / "control.json",
            command=command,
            source="tui",
            reason=reason,
        )

    def action_pause(self) -> None:
        self._write_control_command("pause", reason="paused from TUI hotkey")
        self.notify("Experiment paused")

    def action_resume(self) -> None:
        self._write_control_command("resume")
        self.notify("Experiment resumed")

    def action_skip(self) -> None:
        self._write_control_command("skip_current")
        self.notify("Skipping current frontier item")

    def action_gpu_status(self) -> None:
        gpu_path = self.research_dir / "gpu_status.json"
        gpus = []
        if gpu_path.exists():
            try:
                data = json.loads(gpu_path.read_text())
                if isinstance(data, dict):
                    gpus = data.get("gpus", [])
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        self.push_screen(GPUStatusModal(gpus))

    def action_view_log(self) -> None:
        log_path = str(self.research_dir / "run.log")
        self.push_screen(LogScreen(log_path))

    def action_quit_app(self) -> None:
        self.exit()

    def append_log(self, line: str) -> None:
        """Thread-safe: append a line to the unified log panel."""
        try:
            self.call_from_thread(self._do_append_log, line)
        except RuntimeError:
            pass  # App already closed

    def _do_append_log(self, line: str) -> None:
        try:
            self.query_one("#agent-log", RichLog).write(line)
        except NoMatches:
            pass

    # Keep old names as aliases for backward compatibility
    append_idea_log = append_log
    append_exp_log = append_log
