"""Comprehensive TUI visual simulation — feed realistic data into every widget."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import DataTable

from paperfarm.state import ResearchState
from paperfarm.tui.app import ResearchApp
from paperfarm.tui.widgets import (
    FrontierPanel,
    LogPanel,
    MetricChart,
    PhaseStripBar,
    StatsBar,
    WorkerPanel,
)


def _make_state(tmp_path: Path) -> ResearchState:
    d = tmp_path / ".research"
    d.mkdir(parents=True, exist_ok=True)
    return ResearchState(d)


def _populate_full_state(state: ResearchState) -> None:
    """Write realistic state data touching every file and every widget."""

    # 1. graph.json — hypotheses + frontier
    graph = {
        "repo_profile": {"name": "bench-project"},
        "hypotheses": [
            {"id": "H-1", "text": "JIT compile improves latency"},
            {"id": "H-2", "text": "Vectorized ops reduce overhead"},
            {"id": "H-3", "text": "Cache alignment helps throughput"},
        ],
        "experiment_specs": [],
        "evidence": [],
        "claim_updates": [],
        "branch_relations": [],
        "frontier": [
            {"id": "F-1", "priority": 0.9, "status": "archived", "description": "JIT compile benchmark"},
            {"id": "F-2", "priority": 0.7, "status": "running", "description": "Vectorized matmul"},
            {"id": "F-3", "priority": 0.5, "status": "pending", "description": "Cache-aligned alloc"},
            {"id": "F-4", "priority": 0.3, "status": "rejected", "description": "Random seed ablation"},
        ],
        "counters": {"hypothesis": 3, "spec": 0, "frontier": 4, "evidence": 0, "claim": 0},
    }
    state.save_graph(graph)

    # 2. activity.json — phase, round, workers
    state.save_activity({
        "phase": "experiment",
        "round": 3,
        "workers": [
            {"id": "w0", "status": "running", "gpu": "cuda:0", "frontier_id": "F-2"},
            {"id": "w1", "status": "idle", "gpu": "cuda:1", "frontier_id": ""},
        ],
        "control": {"paused": False, "skip_current": False},
    })

    # 3. results.tsv — mix of keep/reject
    state.append_result({
        "worker": "w0", "frontier_id": "F-1", "status": "keep",
        "metric": "latency_ms", "value": "12.3", "description": "JIT baseline",
    })
    state.append_result({
        "worker": "w0", "frontier_id": "F-1", "status": "keep",
        "metric": "latency_ms", "value": "9.8", "description": "JIT opt v2",
    })
    state.append_result({
        "worker": "w0", "frontier_id": "F-4", "status": "reject",
        "metric": "latency_ms", "value": "15.1", "description": "Random seed no effect",
    })
    state.append_result({
        "worker": "w0", "frontier_id": "F-2", "status": "keep",
        "metric": "latency_ms", "value": "7.2", "description": "Vec matmul v1",
    })

    # 4. log.jsonl — diverse event types
    state.append_log({"event": "session_started"})
    state.append_log({"event": "skill_started", "step": "scout", "skill": "scout.md"})
    state.append_log({"event": "agent_output", "phase": "scout", "line": "Analyzing repository structure..."})
    state.append_log({"event": "agent_output", "phase": "scout", "line": "Found 3 source files, 2 benchmarks"})
    state.append_log({"event": "skill_completed", "step": "scout", "skill": "scout.md", "exit_code": 0})
    state.append_log({"event": "round_started", "round": 1})
    state.append_log({"event": "skill_started", "step": "manager", "skill": "manager.md"})
    state.append_log({"event": "agent_output", "phase": "manager", "line": "Generating hypotheses..."})
    state.append_log({"event": "skill_completed", "step": "manager", "skill": "manager.md", "exit_code": 0})
    state.append_log({"event": "skill_started", "step": "critic", "skill": "critic.md"})
    state.append_log({"event": "skill_completed", "step": "critic", "skill": "critic.md", "exit_code": 0})
    state.append_log({"event": "skill_started", "step": "experiment", "skill": "experiment.md"})
    state.append_log({"event": "worker_started", "worker": "w0", "frontier_id": "F-1"})
    state.append_log({"event": "experiment_result", "message": "F-1: latency=12.3ms (keep)"})
    state.append_log({"event": "experiment_result", "message": "F-1: latency=9.8ms (keep, improved!)"})
    state.append_log({"event": "worker_finished", "worker": "w0", "frontier_id": "F-1"})
    state.append_log({"event": "skill_completed", "step": "experiment", "skill": "experiment.md", "exit_code": 0})
    state.append_log({"event": "round_completed", "round": 1})
    state.append_log({"event": "round_started", "round": 2})
    state.append_log({"event": "skill_started", "step": "manager", "skill": "manager.md"})
    state.append_log({"event": "skill_completed", "step": "manager", "skill": "manager.md", "exit_code": 0})
    state.append_log({"event": "skill_started", "step": "experiment", "skill": "experiment.md"})
    state.append_log({"event": "worker_started", "worker": "w0", "frontier_id": "F-2"})
    state.append_log({"event": "agent_output", "phase": "experiment", "line": "Running vectorized matmul..."})


def _populate_failed_state(state: ResearchState) -> None:
    """State for a session that failed at bootstrap."""
    state.save_activity({
        "phase": "failed",
        "round": 0,
        "workers": [],
        "control": {"paused": False, "skip_current": False},
    })
    state.append_log({"event": "session_started"})
    state.append_log({"event": "skill_started", "step": "scout", "skill": "scout.md"})
    state.append_log({"event": "agent_output", "phase": "scout", "line": "Error: missing bearer token"})
    state.append_log({"event": "skill_completed", "step": "scout", "skill": "scout.md", "exit_code": 1})
    state.append_log({
        "event": "session_ended", "status": "failed",
        "stage": "bootstrap", "exit_code": 1,
    })


def _populate_crashed_state(state: ResearchState) -> None:
    """State for a session where the runner threw an exception."""
    state.save_activity({
        "phase": "crashed",
        "round": 1,
        "workers": [{"id": "w0", "status": "error", "gpu": "cuda:0", "frontier_id": "F-1"}],
        "control": {"paused": False, "skip_current": False},
    })
    state.append_log({"event": "session_started"})
    state.append_log({"event": "skill_started", "step": "scout", "skill": "scout.md"})
    state.append_log({"event": "skill_completed", "step": "scout", "skill": "scout.md", "exit_code": 0})
    state.append_log({"event": "round_started", "round": 1})
    state.append_log({
        "event": "session_ended", "status": "crashed",
        "error": "Traceback: FileNotFoundError: skill file missing",
    })


def _populate_paused_state(state: ResearchState) -> None:
    """State for a paused session."""
    state.save_activity({
        "phase": "manager",
        "round": 2,
        "workers": [{"id": "w0", "status": "paused", "gpu": "cuda:0", "frontier_id": "F-1"}],
        "control": {"paused": True, "skip_current": False},
    })
    state.save_graph({
        "hypotheses": [{"id": "H-1", "text": "test"}],
        "frontier": [{"id": "F-1", "priority": 0.8, "status": "running", "description": "Test exp"}],
        "counters": {"hypothesis": 1, "frontier": 1},
    })
    state.append_log({"event": "session_started"})
    state.append_log({"event": "loop_paused", "round": 2})


# ---------------------------------------------------------------------------
# Tests: Happy path — full data
# ---------------------------------------------------------------------------


class TestFullDataDisplay:
    """Feed realistic data and verify every widget renders correctly."""

    @pytest.mark.asyncio
    async def test_statsbar_shows_all_fields(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            stats = app.query_one("#stats", StatsBar)
            content = str(stats.content)
            assert "experiment" in content  # phase
            assert "3" in content           # round
            assert "3" in content           # hypotheses
            assert "Best:" in content

    @pytest.mark.asyncio
    async def test_phase_bar_highlights_experiment(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            phase_bar = app.query_one("#phase", PhaseStripBar)
            content = str(phase_bar.content)
            assert "EXPERIMENT" in content  # active phase uppercased

    @pytest.mark.asyncio
    async def test_frontier_table_sorted_by_priority(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            table: DataTable = app.query_one("#frontier-table", DataTable)
            assert table.row_count == 4
            # Highest priority first
            first_row = table.get_row_at(0)
            assert "F-1" in str(first_row)

    @pytest.mark.asyncio
    async def test_worker_table_shows_both_workers(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            table: DataTable = app.query_one("#worker-table", DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_log_panel_shows_all_event_types(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            log_panel = app.query_one("#log", LogPanel)
            assert log_panel._seen_count > 0

    @pytest.mark.asyncio
    async def test_metric_chart_renders_kept_results(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            chart = app.query_one("#chart", MetricChart)
            content = str(chart.content)
            # Should show chart or values (3 kept results)
            assert "No kept results" not in content

    @pytest.mark.asyncio
    async def test_incremental_log_update(self, tmp_path: Path) -> None:
        """Second poll should only append new events, not duplicate."""
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            log_panel = app.query_one("#log", LogPanel)
            count_after_first = log_panel._seen_count

            # Add one more event
            state.append_log({"event": "agent_output", "line": "new output line"})
            await app._poll_state()
            assert log_panel._seen_count == count_after_first + 1


# ---------------------------------------------------------------------------
# Tests: Failed session
# ---------------------------------------------------------------------------


class TestFailedSessionDisplay:
    """Verify the TUI correctly shows a failed session."""

    @pytest.mark.asyncio
    async def test_statsbar_shows_failed(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_failed_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            stats = app.query_one("#stats", StatsBar)
            content = str(stats.content)
            assert "FAILED" in content

    @pytest.mark.asyncio
    async def test_phase_bar_shows_failed_marker(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_failed_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            phase_bar = app.query_one("#phase", PhaseStripBar)
            content = str(phase_bar.content)
            assert "FAILED" in content

    @pytest.mark.asyncio
    async def test_log_shows_fail_and_session_end(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_failed_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            log_panel = app.query_one("#log", LogPanel)
            # Should have seen all events including session_ended
            assert log_panel._seen_count == 5

    @pytest.mark.asyncio
    async def test_no_duplicate_runner_crash(self, tmp_path: Path) -> None:
        """Multiple polls should NOT produce duplicate error messages."""
        state = _make_state(tmp_path)
        _populate_failed_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            await app._poll_state()
            await app._poll_state()
            log_panel = app.query_one("#log", LogPanel)
            # Seen count should not grow beyond actual events
            assert log_panel._seen_count == 5


# ---------------------------------------------------------------------------
# Tests: Crashed session
# ---------------------------------------------------------------------------


class TestCrashedSessionDisplay:

    @pytest.mark.asyncio
    async def test_statsbar_shows_crashed(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_crashed_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            content = str(app.query_one("#stats", StatsBar).content)
            assert "CRASHED" in content


# ---------------------------------------------------------------------------
# Tests: Paused session
# ---------------------------------------------------------------------------


class TestPausedSessionDisplay:

    @pytest.mark.asyncio
    async def test_statsbar_shows_paused(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_paused_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            content = str(app.query_one("#stats", StatsBar).content)
            assert "PAUSED" in content

    @pytest.mark.asyncio
    async def test_frontier_shows_running(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _populate_paused_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            table: DataTable = app.query_one("#frontier-table", DataTable)
            assert table.row_count == 1


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_empty_state_all_widgets_safe(self, tmp_path: Path) -> None:
        """Every widget handles empty data without error."""
        state = _make_state(tmp_path)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            assert app.query_one("#stats", StatsBar) is not None

    @pytest.mark.asyncio
    async def test_log_rotation_resets_seen_count(self, tmp_path: Path) -> None:
        """If log gets shorter (new session), _seen_count resets."""
        state = _make_state(tmp_path)
        for i in range(10):
            state.append_log({"event": "agent_output", "line": f"line {i}"})

        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            await app._poll_state()
            assert app.query_one("#log", LogPanel)._seen_count == 10

            # Simulate log rotation (new session clears log)
            log_path = state.dir / "log.jsonl"
            log_path.write_text("")
            state.append_log({"event": "session_started"})

            await app._poll_state()
            assert app.query_one("#log", LogPanel)._seen_count == 1

    @pytest.mark.asyncio
    async def test_many_rapid_polls_no_duplication(self, tmp_path: Path) -> None:
        """20 rapid polls should produce same widget state as 1 poll."""
        state = _make_state(tmp_path)
        _populate_full_state(state)
        app = ResearchApp(repo_path=str(tmp_path), state=state)
        async with app.run_test() as pilot:
            for _ in range(20):
                await app._poll_state()
            log_panel = app.query_one("#log", LogPanel)
            # Seen count should match actual events, not 20x
            events = state.tail_log(50)
            assert log_panel._seen_count == len(events)
