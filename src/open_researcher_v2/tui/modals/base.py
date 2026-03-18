"""Base class for review modal screens."""
from __future__ import annotations

from textual.binding import Binding
from textual.screen import Screen

from open_researcher_v2.state import ResearchState


class ReviewScreen(Screen):
    """Base class for all review modals.

    Subclasses implement ``compose()`` for layout and ``_apply_decisions()``
    for writing user choices to state files.
    """

    BINDINGS = [
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "skip", "Skip"),
    ]

    def __init__(
        self,
        state: ResearchState,
        review_request: dict,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.state = state
        self.review_request = review_request

    def _apply_decisions(self) -> None:
        """Subclass hook: write user decisions to graph.json / files."""

    def action_confirm(self) -> None:
        self._apply_decisions()
        self.state.clear_awaiting_review()
        self.dismiss(True)

    def action_skip(self) -> None:
        self.state.clear_awaiting_review()
        self.state.append_log({
            "event": "review_skipped",
            "review_type": self.review_request.get("type", "unknown"),
        })
        self.dismiss(None)
