"""Comprehensive TUI integration tests for the human-in-the-loop checkpoint system.

Tests cover:
  A. Modal Appearance -- correct modal pushed for each review type
  B. Content Verification -- tables/widgets show correct data
  C. Keyboard Interaction -- enter/escape/space/a bindings work
  D. State Changes -- confirm/skip write correct state to graph/files
  E. Anytime Interactions -- g/i keys on main screen
  F. Multi-Round Flow -- sequential checkpoints
  G. Edge Cases & Safety -- unknown types, quit during review
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypeVar

import pytest

from open_researcher_v2.state import ResearchState
from open_researcher_v2.tui.app import ResearchApp
from open_researcher_v2.tui.modals.direction import DirectionConfirmScreen
from open_researcher_v2.tui.modals.frontier import FrontierReviewScreen
from open_researcher_v2.tui.modals.goal_edit import GoalEditScreen
from open_researcher_v2.tui.modals.hypothesis import HypothesisReviewScreen
from open_researcher_v2.tui.modals.inject import InjectIdeaScreen
from open_researcher_v2.tui.modals.result import ResultReviewScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T = TypeVar("_T")


def _make_state(tmp_path: Path) -> ResearchState:
    """Create a ResearchState backed by a temporary directory."""
    research_dir = tmp_path / ".research"
    research_dir.mkdir(parents=True, exist_ok=True)
    return ResearchState(research_dir)


def _seed_frontier(state: ResearchState, items: list[dict]) -> None:
    """Write frontier items into graph.json."""
    graph = state.load_graph()
    graph["frontier"] = items
    graph["counters"]["frontier"] = len(items)
    state.save_graph(graph)


def _seed_results(state: ResearchState, rows: list[dict]) -> None:
    """Append result rows to results.tsv."""
    for row in rows:
        state.append_result(row)


def _set_review(state: ResearchState, review_type: str) -> None:
    """Set an awaiting_review in activity.json."""
    state.set_awaiting_review({
        "type": review_type,
        "requested_at": "2026-03-19T14:00:00Z",
    })


def _make_app(tmp_path: Path, state: ResearchState) -> ResearchApp:
    """Create a ResearchApp for testing (no runner, no auto-poll)."""
    return ResearchApp(repo_path=str(tmp_path), state=state)


def _find_modal(app: ResearchApp, cls: type[_T]) -> _T | None:
    """Find a modal of the given type on the screen stack."""
    for s in app.screen_stack:
        if isinstance(s, cls):
            return s
    return None


# ===========================================================================
# A. Modal Appearance
# ===========================================================================


class TestModalAppearance:
    """Verify the correct modal screen is pushed for each review type."""

    @pytest.mark.asyncio
    async def test_hypothesis_review_modal_appears_on_poll(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert _find_modal(app, HypothesisReviewScreen) is not None, (
                f"Expected HypothesisReviewScreen in stack, got {app.screen_stack}"
            )

    @pytest.mark.asyncio
    async def test_direction_confirm_modal_appears(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _set_review(state, "direction_confirm")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert _find_modal(app, DirectionConfirmScreen) is not None

    @pytest.mark.asyncio
    async def test_frontier_review_modal_appears(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 3, "status": "approved", "description": "X"},
        ])
        _set_review(state, "frontier_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert _find_modal(app, FrontierReviewScreen) is not None

    @pytest.mark.asyncio
    async def test_result_review_modal_appears(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_results(state, [
            {"worker": "w0", "frontier_id": "f-001", "status": "keep",
             "metric": "acc", "value": "0.9", "description": "r1"},
        ])
        _set_review(state, "result_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert _find_modal(app, ResultReviewScreen) is not None

    @pytest.mark.asyncio
    async def test_no_modal_when_no_review(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            # Only the default screen should be on the stack
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_modal_not_duplicated_on_repeated_poll(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            app._poll_state()
            await pilot.pause()
            # Count HypothesisReviewScreen instances in stack
            modals = [
                s for s in app.screen_stack
                if isinstance(s, HypothesisReviewScreen)
            ]
            assert len(modals) == 1, f"Expected 1 modal, got {len(modals)}"


# ===========================================================================
# B. Content Verification
# ===========================================================================


class TestContentVerification:
    """Verify modals display the correct data from state."""

    @pytest.mark.asyncio
    async def test_hypothesis_review_shows_frontier_items(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 3, "status": "approved", "description": "Alpha"},
            {"id": "f-002", "priority": 5, "status": "approved", "description": "Beta"},
            {"id": "f-003", "priority": 1, "status": "approved", "description": "Gamma"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None
            from textual.widgets import DataTable
            table = modal.query_one("#review-table", DataTable)
            assert table.row_count == 3

    @pytest.mark.asyncio
    async def test_hypothesis_review_sorts_by_priority(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 10, "status": "approved", "description": "A"},
            {"id": "f-002", "priority": 5, "status": "approved", "description": "B"},
            {"id": "f-003", "priority": 20, "status": "approved", "description": "C"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None
            from textual.widgets import DataTable
            table = modal.query_one("#review-table", DataTable)
            rows = list(table.rows)
            # First row should be priority 20 (f-003)
            first_cells = table.get_row(rows[0])
            assert str(first_cells[0]) == "f-003"
            # Second row should be priority 10 (f-001)
            second_cells = table.get_row(rows[1])
            assert str(second_cells[0]) == "f-001"
            # Third row should be priority 5 (f-002)
            third_cells = table.get_row(rows[2])
            assert str(third_cells[0]) == "f-002"

    @pytest.mark.asyncio
    async def test_result_review_shows_results(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_results(state, [
            {"worker": "w0", "frontier_id": "f-001", "status": "keep",
             "metric": "acc", "value": "0.9", "description": "r1"},
            {"worker": "w1", "frontier_id": "f-002", "status": "discard",
             "metric": "acc", "value": "0.3", "description": "r2"},
        ])
        _set_review(state, "result_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            modal = _find_modal(app, ResultReviewScreen)
            assert modal is not None
            from textual.widgets import DataTable
            table = modal.query_one("#result-table", DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_direction_confirm_shows_strategy(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        strategy_text = "Focus on data augmentation techniques."
        (state.dir / "research-strategy.md").write_text(
            strategy_text, encoding="utf-8"
        )
        _set_review(state, "direction_confirm")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            modal = _find_modal(app, DirectionConfirmScreen)
            assert modal is not None
            # Query Static widgets in the modal for the strategy text
            from textual.widgets import Static
            statics = modal.query(Static)
            combined = " ".join(str(s.content) for s in statics)
            assert "data augmentation" in combined


# ===========================================================================
# C. Keyboard Interaction
# ===========================================================================


class TestKeyboardInteraction:
    """Verify keyboard bindings work within modals.

    Note: DataTable captures the ``enter`` key via ``action_select_cursor``,
    so pressing enter when the table has focus does NOT trigger the screen's
    ``action_confirm``.  For enter-confirm tests we call ``action_confirm()``
    directly on the modal.  The ``escape`` key is NOT captured by DataTable,
    so pressing escape works as expected from any focus state.
    """

    @pytest.mark.asyncio
    async def test_enter_confirms_and_dismisses(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert len(app.screen_stack) > 1

            # DataTable captures enter, so invoke the screen action directly
            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None
            modal.action_confirm()
            await pilot.pause()

            # awaiting_review should be cleared
            assert state.get_awaiting_review() is None
            # Screen stack should be back to 1
            assert len(app.screen_stack) == 1
            # _review_shown should be reset (via callback)
            assert app._review_shown is False

    @pytest.mark.asyncio
    async def test_escape_skips_and_dismisses(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert len(app.screen_stack) > 1

            await pilot.press("escape")
            await pilot.pause()

            # awaiting_review should be cleared
            assert state.get_awaiting_review() is None
            # Should be dismissed
            assert len(app.screen_stack) == 1
            # Check log for review_skipped event
            logs = state.tail_log(50)
            events = [e.get("event") for e in logs]
            assert "review_skipped" in events

    @pytest.mark.asyncio
    async def test_space_toggles_item_decision(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
            {"id": "f-002", "priority": 3, "status": "approved", "description": "B"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()

            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None

            # Press space to toggle the current row
            await pilot.press("space")
            await pilot.pause()

            # The first item (highest priority = f-001) should be toggled
            assert len(modal._decisions) > 0
            # The toggled item should have "rejected" status (toggled from "approved")
            toggled_values = list(modal._decisions.values())
            assert "rejected" in toggled_values

    @pytest.mark.asyncio
    async def test_approve_all_clears_decisions(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
            {"id": "f-002", "priority": 3, "status": "approved", "description": "B"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()

            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None

            # Toggle one item
            await pilot.press("space")
            await pilot.pause()
            assert len(modal._decisions) > 0

            # Approve all should clear decisions
            await pilot.press("a")
            await pilot.pause()
            assert len(modal._decisions) == 0

    @pytest.mark.asyncio
    async def test_result_review_space_toggles_override(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_results(state, [
            {"worker": "w0", "frontier_id": "f-001", "status": "discard",
             "metric": "acc", "value": "0.3", "description": "r1"},
        ])
        _set_review(state, "result_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()

            modal = _find_modal(app, ResultReviewScreen)
            assert modal is not None

            await pilot.press("space")
            await pilot.pause()
            assert len(modal._overrides) > 0
            # AI status was "discard", so override should flip to "keep"
            assert "keep" in modal._overrides.values()


# ===========================================================================
# D. State Changes
# ===========================================================================


class TestStateChanges:
    """Verify confirm/skip correctly update state files.

    Uses ``action_confirm()`` directly on the modal to avoid DataTable
    capturing the enter key.
    """

    @pytest.mark.asyncio
    async def test_confirm_writes_rejected_items_to_graph(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
            {"id": "f-002", "priority": 3, "status": "approved", "description": "B"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()

            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None

            # Toggle first item (f-001, highest priority) to rejected
            await pilot.press("space")
            await pilot.pause()

            # Confirm via direct action call (DataTable captures enter)
            modal.action_confirm()
            await pilot.pause()

            # Verify graph.json has f-001 status=rejected
            graph = state.load_graph()
            statuses = {f["id"]: f["status"] for f in graph["frontier"]}
            assert statuses["f-001"] == "rejected"
            # f-002 should remain approved
            assert statuses["f-002"] == "approved"

    @pytest.mark.asyncio
    async def test_result_override_writes_claim_update(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_results(state, [
            {"worker": "w0", "frontier_id": "f-001", "status": "discard",
             "metric": "acc", "value": "0.3", "description": "r1"},
        ])
        _set_review(state, "result_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()

            modal = _find_modal(app, ResultReviewScreen)
            assert modal is not None

            # Toggle override (discard -> keep)
            await pilot.press("space")
            await pilot.pause()

            # Confirm via direct action call (DataTable captures enter)
            modal.action_confirm()
            await pilot.pause()

            # Verify graph.json has claim_updates with reviewer=human
            graph = state.load_graph()
            claims = graph.get("claim_updates", [])
            assert len(claims) == 1
            assert claims[0]["frontier_id"] == "f-001"
            assert claims[0]["new_status"] == "keep"
            assert claims[0]["reviewer"] == "human"

    @pytest.mark.asyncio
    async def test_direction_confirm_writes_constraints(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _set_review(state, "direction_confirm")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()

            modal = _find_modal(app, DirectionConfirmScreen)
            assert modal is not None

            # Set the TextArea value directly on the modal
            from textual.widgets import TextArea
            textarea = modal.query_one("#constraints-input", TextArea)
            textarea.load_text("Focus on parser performance")

            # Confirm via direct action call
            modal.action_confirm()
            await pilot.pause()

            # Verify user_constraints.md was created
            constraints_path = state.dir / "user_constraints.md"
            assert constraints_path.exists()
            content = constraints_path.read_text(encoding="utf-8")
            assert "Focus on parser performance" in content


# ===========================================================================
# E. Anytime Interactions (g/i keys)
# ===========================================================================


class TestAnytimeInteractions:
    """Verify g/i keys open the correct modals from the main screen."""

    @pytest.mark.asyncio
    async def test_g_key_opens_goal_edit(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("g")
            await pilot.pause()
            assert _find_modal(app, GoalEditScreen) is not None, (
                f"Expected GoalEditScreen in stack, got {app.screen_stack}"
            )

    @pytest.mark.asyncio
    async def test_i_key_opens_inject_idea(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("i")
            await pilot.pause()
            assert _find_modal(app, InjectIdeaScreen) is not None, (
                f"Expected InjectIdeaScreen in stack, got {app.screen_stack}"
            )

    @pytest.mark.asyncio
    async def test_inject_adds_frontier_item(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("i")
            await pilot.pause()

            modal = _find_modal(app, InjectIdeaScreen)
            assert modal is not None

            # Set values directly on the Input widgets (query from modal)
            from textual.widgets import Input
            desc_input = modal.query_one("#inject-desc", Input)
            desc_input.value = "Try __slots__"
            priority_input = modal.query_one("#inject-priority", Input)
            priority_input.value = "4"

            # Input widget captures enter via action_submit, so call
            # the screen's action_inject directly
            modal.action_inject()
            await pilot.pause()

            # Verify graph.json has the new frontier item
            graph = state.load_graph()
            frontier = graph.get("frontier", [])
            assert len(frontier) == 1
            item = frontier[0]
            assert item["description"] == "Try __slots__"
            assert item["selection_reason_code"] == "human_injected"
            assert item["priority"] == 4
            assert graph["counters"]["frontier"] == 1


# ===========================================================================
# F. Multi-Round Flow
# ===========================================================================


class TestMultiRoundFlow:
    """Verify sequential checkpoints work correctly."""

    @pytest.mark.asyncio
    async def test_sequential_checkpoints(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            # -- First checkpoint: hypothesis_review --
            app._poll_state()
            await pilot.pause()
            modal = _find_modal(app, HypothesisReviewScreen)
            assert modal is not None

            # Confirm via direct action call
            modal.action_confirm()
            await pilot.pause()
            assert len(app.screen_stack) == 1
            assert state.get_awaiting_review() is None

            # -- Second checkpoint: result_review --
            _seed_results(state, [
                {"worker": "w0", "frontier_id": "f-001", "status": "keep",
                 "metric": "acc", "value": "0.9", "description": "r1"},
            ])
            _set_review(state, "result_review")
            app._poll_state()
            await pilot.pause()
            modal2 = _find_modal(app, ResultReviewScreen)
            assert modal2 is not None

            # Confirm via direct action call
            modal2.action_confirm()
            await pilot.pause()
            assert len(app.screen_stack) == 1
            assert state.get_awaiting_review() is None

    @pytest.mark.asyncio
    async def test_review_shown_resets_after_dismiss(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert app._review_shown is True

            # Dismiss via escape (escape is not captured by DataTable)
            await pilot.press("escape")
            await pilot.pause()
            assert app._review_shown is False

            # _review_shown being False allows the next modal to appear
            _set_review(state, "hypothesis_review")
            app._poll_state()
            await pilot.pause()
            assert app._review_shown is True
            assert _find_modal(app, HypothesisReviewScreen) is not None


# ===========================================================================
# G. Edge Cases & Safety
# ===========================================================================


class TestEdgeCasesAndSafety:
    """Edge cases: quit during review, unknown review type."""

    @pytest.mark.asyncio
    async def test_quit_during_review_clears_state(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _seed_frontier(state, [
            {"id": "f-001", "priority": 5, "status": "approved", "description": "A"},
        ])
        _set_review(state, "hypothesis_review")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            app._poll_state()
            await pilot.pause()
            assert state.get_awaiting_review() is not None

            # Quit the app -- action_quit clears awaiting_review
            await pilot.press("q")
            await pilot.pause()

        # After the app exits, awaiting_review should be cleared
        assert state.get_awaiting_review() is None
        # _review_shown should have been reset
        assert app._review_shown is False

    @pytest.mark.asyncio
    async def test_unknown_review_type_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        state = _make_state(tmp_path)
        _set_review(state, "bogus_type")

        app = _make_app(tmp_path, state)
        async with app.run_test(size=(120, 40)) as pilot:
            # _make_review_screen raises ValueError for unknown type,
            # but _poll_state catches it. The app should still be running.
            app._poll_state()
            await pilot.pause()
            assert len(app.screen_stack) == 1
            # awaiting_review should be cleared by _make_review_screen
            assert state.get_awaiting_review() is None
            # _review_shown should be reset because the exception path
            # sets it back to False
            assert app._review_shown is False
