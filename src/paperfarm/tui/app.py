"""TUI main application for PaperFarm.

Provides :class:`ResearchApp`, a Textual application that polls
:class:`ResearchState` every second and pushes updates to the widgets.
An optional *runner* callable is started in a daemon thread so the TUI
can monitor a live research session.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from typing import Any, Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, TabbedContent, TabPane

from paperfarm.state import ResearchState
from paperfarm.tui.widgets import (
    FrontierPanel,
    LogPanel,
    MetricChart,
    PhaseStripBar,
    StatsBar,
    WorkerPanel,
)

logger = logging.getLogger(__name__)


class ResearchApp(App):
    """Polling-based TUI for monitoring and controlling a research session."""

    CSS_PATH = "styles.css"
    TITLE = "PaperFarm"

    BINDINGS = [
        Binding("p", "pause", "Pause"),
        Binding("r", "resume", "Resume"),
        Binding("s", "skip", "Skip"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        repo_path: str,
        state: ResearchState,
        runner: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.repo_path = repo_path
        self.state = state
        self.runner = runner
        self._runner_thread: threading.Thread | None = None
        # Only set for unhandled exceptions in runner (not normal exit codes).
        self._runner_error: str | None = None
        self._error_shown = False

    # -- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatsBar(id="stats")
        yield PhaseStripBar(id="phase")
        with TabbedContent():
            with TabPane("Execution", id="tab-exec"):
                with Horizontal():
                    yield FrontierPanel(id="frontier")
                    yield WorkerPanel(id="workers")
            with TabPane("Metrics", id="tab-metrics"):
                yield MetricChart(id="chart")
            with TabPane("Logs", id="tab-logs"):
                yield LogPanel(id="log")
        yield Footer()

    # -- lifecycle ----------------------------------------------------------

    def on_mount(self) -> None:
        self.set_interval(1.0, self._poll_state)
        if self.runner is not None:
            self._runner_thread = threading.Thread(
                target=self._run_runner, daemon=True, name="pf-runner"
            )
            self._runner_thread.start()

    def _run_runner(self) -> None:
        """Execute the runner callable.

        Normal failures (non-zero rc) are reported via state events
        (session_ended). Only unhandled exceptions are captured here.
        """
        try:
            if self.runner is not None:
                self.runner()
        except Exception:
            tb = traceback.format_exc()
            self._runner_error = tb
            logger.exception("Runner thread crashed")
            # Try to record it in state so the log panel picks it up
            try:
                self.state.update_phase("crashed")
                self.state.append_log({
                    "event": "session_ended",
                    "status": "crashed",
                    "error": tb[:500],
                })
            except Exception:
                pass

    # -- polling (non-blocking) ---------------------------------------------

    def _read_state_sync(self) -> dict[str, Any]:
        """Read all state files (runs in thread pool, NOT event loop)."""
        summary = self.state.summary()
        graph = summary.pop("_graph", None) or self.state.load_graph()
        events = self.state.tail_log(50)
        results = self.state.load_results()
        return {
            "summary": summary,
            "frontier": graph.get("frontier", []),
            "events": events,
            "results": results,
        }

    async def _poll_state(self) -> None:
        """Poll state in a thread, then update widgets on the main loop."""
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._read_state_sync)
        except Exception:
            logger.debug("poll read failed", exc_info=True)
            return

        try:
            summary = data["summary"]

            stats: StatsBar = self.query_one("#stats", StatsBar)
            stats.update_data(summary)

            phase_bar: PhaseStripBar = self.query_one("#phase", PhaseStripBar)
            phase_bar.update_phase(summary.get("phase", "idle"))

            frontier: FrontierPanel = self.query_one("#frontier", FrontierPanel)
            frontier.update_data(data["frontier"])

            workers: WorkerPanel = self.query_one("#workers", WorkerPanel)
            workers.update_data(summary.get("workers", []))

            log_panel: LogPanel = self.query_one("#log", LogPanel)
            log_panel.update_data(data["events"])

            chart: MetricChart = self.query_one("#chart", MetricChart)
            chart.update_data(data["results"])
        except Exception:
            logger.debug("poll widget update failed", exc_info=True)

    # -- actions ------------------------------------------------------------

    def action_pause(self) -> None:
        try:
            self.state.set_paused(True)
        except Exception:
            logger.debug("pause failed", exc_info=True)

    def action_resume(self) -> None:
        try:
            self.state.set_paused(False)
        except Exception:
            logger.debug("resume failed", exc_info=True)

    def action_skip(self) -> None:
        try:
            self.state.set_skip_current(True)
        except Exception:
            logger.debug("skip failed", exc_info=True)
