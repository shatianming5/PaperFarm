"""Tests for TUI review modal screens."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from open_researcher_v2.state import ResearchState


class TestReviewScreenBase:
    def test_import(self):
        from open_researcher_v2.tui.modals.base import ReviewScreen
        assert ReviewScreen is not None

    def test_action_skip_clears_review(self, tmp_path):
        from open_researcher_v2.tui.modals.base import ReviewScreen
        research_dir = tmp_path / ".research"
        research_dir.mkdir()
        state = ResearchState(research_dir)
        state.set_awaiting_review({"type": "test", "requested_at": "2026-03-19T14:00:00Z"})
        screen = ReviewScreen(state=state, review_request={"type": "test"})
        screen.dismiss = MagicMock()
        screen.action_skip()
        assert state.get_awaiting_review() is None
        screen.dismiss.assert_called_once_with(None)


class TestDirectionConfirmScreen:
    def test_import(self):
        from open_researcher_v2.tui.modals.direction import DirectionConfirmScreen
        assert DirectionConfirmScreen is not None

    def test_confirm_writes_constraints(self, tmp_path):
        from open_researcher_v2.tui.modals.direction import DirectionConfirmScreen
        research_dir = tmp_path / ".research"
        research_dir.mkdir()
        state = ResearchState(research_dir)
        state.set_awaiting_review({"type": "direction_confirm", "requested_at": "2026-03-19T14:00:00Z"})
        screen = DirectionConfirmScreen(state=state, review_request={"type": "direction_confirm"})
        screen._user_constraints = "Focus on parser only"
        screen.dismiss = MagicMock()
        screen._apply_decisions()
        content = (research_dir / "user_constraints.md").read_text()
        assert "Focus on parser only" in content


class TestHypothesisReviewScreen:
    def test_apply_rejects_item(self, tmp_path):
        from open_researcher_v2.tui.modals.hypothesis import HypothesisReviewScreen
        research_dir = tmp_path / ".research"
        research_dir.mkdir()
        state = ResearchState(research_dir)
        graph = state.load_graph()
        graph["frontier"] = [
            {"id": "frontier-001", "priority": 3, "status": "approved", "description": "Test A"},
            {"id": "frontier-002", "priority": 2, "status": "approved", "description": "Test B"},
        ]
        state.save_graph(graph)
        screen = HypothesisReviewScreen(state=state, review_request={"type": "hypothesis_review"})
        screen._decisions = {"frontier-002": "rejected"}
        screen.dismiss = MagicMock()
        screen._apply_decisions()
        graph = state.load_graph()
        statuses = {f["id"]: f["status"] for f in graph["frontier"]}
        assert statuses["frontier-001"] == "approved"
        assert statuses["frontier-002"] == "rejected"


class TestResultReviewScreen:
    def test_override_writes_claim_update(self, tmp_path):
        from open_researcher_v2.tui.modals.result import ResultReviewScreen
        research_dir = tmp_path / ".research"
        research_dir.mkdir()
        state = ResearchState(research_dir)
        state.append_result({
            "timestamp": "2026-03-19T14:00:00Z",
            "worker": "w0",
            "frontier_id": "frontier-001",
            "status": "discard",
            "metric": "ops_per_sec",
            "value": "2000000",
            "description": "Test result",
        })
        screen = ResultReviewScreen(state=state, review_request={"type": "result_review"})
        screen._overrides = {"frontier-001": "keep"}
        screen.dismiss = MagicMock()
        screen._apply_decisions()
        graph = state.load_graph()
        claims = graph.get("claim_updates", [])
        assert len(claims) == 1
        assert claims[0]["frontier_id"] == "frontier-001"
        assert claims[0]["new_status"] == "keep"
        assert claims[0]["reviewer"] == "human"


class TestGoalEditScreen:
    def test_save_writes_constraints(self, tmp_path):
        from open_researcher_v2.tui.modals.goal_edit import GoalEditScreen
        research_dir = tmp_path / ".research"
        research_dir.mkdir()
        state = ResearchState(research_dir)
        screen = GoalEditScreen(state=state)
        screen._user_text = "Focus on parser only"
        screen.dismiss = MagicMock()
        screen.action_save()
        content = (research_dir / "user_constraints.md").read_text()
        assert "Focus on parser only" in content


class TestInjectIdeaScreen:
    def test_inject_adds_to_graph(self, tmp_path):
        from open_researcher_v2.tui.modals.inject import InjectIdeaScreen
        research_dir = tmp_path / ".research"
        research_dir.mkdir()
        state = ResearchState(research_dir)
        screen = InjectIdeaScreen(state=state)
        screen._description = "Try __slots__"
        screen._priority = 3
        screen.dismiss = MagicMock()
        screen.action_inject()
        graph = state.load_graph()
        assert len(graph["frontier"]) == 1
        assert graph["frontier"][0]["description"] == "Try __slots__"
        assert graph["frontier"][0]["selection_reason_code"] == "human_injected"
        assert graph["counters"]["frontier"] == 1


class TestModalsPackageImport:
    def test_all_exports(self):
        from open_researcher_v2.tui.modals import (
            ReviewScreen,
            DirectionConfirmScreen,
            FrontierReviewScreen,
            GoalEditScreen,
            HypothesisReviewScreen,
            InjectIdeaScreen,
            ResultReviewScreen,
        )
        assert all(cls is not None for cls in [
            ReviewScreen, DirectionConfirmScreen, FrontierReviewScreen,
            GoalEditScreen, HypothesisReviewScreen, InjectIdeaScreen,
            ResultReviewScreen,
        ])
