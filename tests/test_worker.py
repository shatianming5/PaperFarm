"""Tests for the WorkerManager."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from open_researcher.idea_pool import IdeaPool
from open_researcher.worker import WorkerManager


def _make_research_dir(tmp: Path) -> Path:
    """Set up a minimal research directory."""
    research = tmp / ".research"
    research.mkdir()
    return research


def _make_idea_pool(research: Path, ideas: list[dict]) -> IdeaPool:
    """Create an idea_pool.json with given ideas."""
    pool_path = research / "idea_pool.json"
    pool_path.write_text(json.dumps({"ideas": ideas}, indent=2))
    return IdeaPool(pool_path)


def test_worker_manager_processes_ideas():
    """All pending ideas should be processed by workers."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = _make_research_dir(tmp_path)

        ideas = [
            {"id": "idea-001", "description": "Test idea 1", "status": "pending",
             "priority": 1, "claimed_by": None, "assigned_experiment": None,
             "result": None, "source": "original", "category": "general",
             "gpu_hint": "auto", "created_at": "2026-01-01T00:00:00"},
            {"id": "idea-002", "description": "Test idea 2", "status": "pending",
             "priority": 2, "claimed_by": None, "assigned_experiment": None,
             "result": None, "source": "original", "category": "general",
             "gpu_hint": "auto", "created_at": "2026-01-01T00:00:00"},
            {"id": "idea-003", "description": "Test idea 3", "status": "pending",
             "priority": 3, "claimed_by": None, "assigned_experiment": None,
             "result": None, "source": "original", "category": "general",
             "gpu_hint": "auto", "created_at": "2026-01-01T00:00:00"},
        ]
        idea_pool = _make_idea_pool(research, ideas)

        # Mock GPU manager that returns no GPUs
        mock_gpu_manager = MagicMock()
        mock_gpu_manager.refresh.return_value = []

        # Track agent run calls
        run_calls = []

        def mock_agent_factory():
            agent = MagicMock()

            def run_side_effect(workdir, on_output=None, program_file="program.md", **kwargs):
                run_calls.append(program_file)
                return 0

            agent.run.side_effect = run_side_effect
            return agent

        output_lines = []

        wm = WorkerManager(
            repo_path=tmp_path,
            research_dir=research,
            gpu_manager=mock_gpu_manager,
            idea_pool=idea_pool,
            agent_factory=mock_agent_factory,
            max_workers=2,
            on_output=output_lines.append,
        )

        wm.start()
        wm.join(timeout=10)

        # All 3 ideas should have been processed
        assert len(run_calls) == 3

        # All ideas should be marked done
        summary = idea_pool.summary()
        assert summary["pending"] == 0
        assert summary["done"] == 3


def test_worker_manager_stops_on_no_ideas():
    """Workers should stop when idea pool is empty."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = _make_research_dir(tmp_path)

        # Empty pool
        idea_pool = _make_idea_pool(research, [])

        mock_gpu_manager = MagicMock()
        mock_gpu_manager.refresh.return_value = []

        mock_agent_factory = MagicMock()

        output_lines = []

        wm = WorkerManager(
            repo_path=tmp_path,
            research_dir=research,
            gpu_manager=mock_gpu_manager,
            idea_pool=idea_pool,
            agent_factory=mock_agent_factory,
            max_workers=2,
            on_output=output_lines.append,
        )

        wm.start()
        wm.join(timeout=5)

        # No agent should have been created/called
        mock_agent_factory.assert_not_called()

        # Workers should have logged "no more pending ideas"
        assert any("No more pending ideas" in line for line in output_lines)


def test_worker_manager_handles_agent_failure():
    """Failed agent runs should mark ideas as skipped, not done."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = _make_research_dir(tmp_path)

        ideas = [
            {"id": "idea-001", "description": "Will fail", "status": "pending",
             "priority": 1, "claimed_by": None, "assigned_experiment": None,
             "result": None, "source": "original", "category": "general",
             "gpu_hint": "auto", "created_at": "2026-01-01T00:00:00"},
        ]
        idea_pool = _make_idea_pool(research, ideas)

        mock_gpu_manager = MagicMock()
        mock_gpu_manager.refresh.return_value = []

        def mock_agent_factory():
            agent = MagicMock()
            agent.run.return_value = 1  # non-zero exit code
            return agent

        output_lines = []

        wm = WorkerManager(
            repo_path=tmp_path,
            research_dir=research,
            gpu_manager=mock_gpu_manager,
            idea_pool=idea_pool,
            agent_factory=mock_agent_factory,
            max_workers=1,
            on_output=output_lines.append,
        )

        wm.start()
        wm.join(timeout=5)

        summary = idea_pool.summary()
        assert summary["pending"] == 0
        assert summary["skipped"] == 1
        assert summary["done"] == 0


def test_worker_manager_handles_agent_exception():
    """Agent exceptions should be caught and idea marked skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = _make_research_dir(tmp_path)

        ideas = [
            {"id": "idea-001", "description": "Will crash", "status": "pending",
             "priority": 1, "claimed_by": None, "assigned_experiment": None,
             "result": None, "source": "original", "category": "general",
             "gpu_hint": "auto", "created_at": "2026-01-01T00:00:00"},
        ]
        idea_pool = _make_idea_pool(research, ideas)

        mock_gpu_manager = MagicMock()
        mock_gpu_manager.refresh.return_value = []

        def mock_agent_factory():
            agent = MagicMock()
            agent.run.side_effect = RuntimeError("Agent crashed")
            return agent

        output_lines = []

        wm = WorkerManager(
            repo_path=tmp_path,
            research_dir=research,
            gpu_manager=mock_gpu_manager,
            idea_pool=idea_pool,
            agent_factory=mock_agent_factory,
            max_workers=1,
            on_output=output_lines.append,
        )

        wm.start()
        wm.join(timeout=5)

        summary = idea_pool.summary()
        assert summary["skipped"] == 1
        assert any("Error" in line for line in output_lines)


def test_worker_manager_stop_signal():
    """Calling stop() should cause workers to exit their loop."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = _make_research_dir(tmp_path)

        # Create many ideas so workers don't run out
        ideas = [
            {"id": f"idea-{i:03d}", "description": f"Idea {i}", "status": "pending",
             "priority": i, "claimed_by": None, "assigned_experiment": None,
             "result": None, "source": "original", "category": "general",
             "gpu_hint": "auto", "created_at": "2026-01-01T00:00:00"}
            for i in range(1, 20)
        ]
        idea_pool = _make_idea_pool(research, ideas)

        mock_gpu_manager = MagicMock()
        mock_gpu_manager.refresh.return_value = []

        import threading

        first_run = threading.Event()

        def mock_agent_factory():
            agent = MagicMock()

            def slow_run(workdir, on_output=None, program_file="program.md", **kwargs):
                first_run.set()
                return 0

            agent.run.side_effect = slow_run
            return agent

        output_lines = []

        wm = WorkerManager(
            repo_path=tmp_path,
            research_dir=research,
            gpu_manager=mock_gpu_manager,
            idea_pool=idea_pool,
            agent_factory=mock_agent_factory,
            max_workers=1,
            on_output=output_lines.append,
        )

        wm.start()
        # Wait for at least one run to complete
        first_run.wait(timeout=5)
        wm.stop()
        wm.join(timeout=5)

        # Not all 19 ideas should have been processed
        summary = idea_pool.summary()
        assert summary["done"] + summary["skipped"] + summary["running"] < 19
