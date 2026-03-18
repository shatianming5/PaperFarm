"""Hypothesis review modal -- shown after manager completes."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Label, Static

from .base import ReviewScreen


class HypothesisReviewScreen(ReviewScreen):
    """Review hypotheses and frontier items proposed by manager."""

    BINDINGS = [
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "skip", "Skip"),
        Binding("space", "toggle_item", "Toggle"),
        Binding("a", "approve_all", "Approve all"),
    ]

    def __init__(self, state, review_request, **kwargs):
        super().__init__(state=state, review_request=review_request, **kwargs)
        self._decisions: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        graph = self.state.load_graph()
        frontier = graph.get("frontier", [])

        with Vertical(id="review-dialog"):
            yield Label("Hypothesis Review", id="review-title")
            table = DataTable(id="review-table")
            table.add_columns("ID", "P", "Status", "Description", "Keep?")
            table.cursor_type = "row"
            for item in sorted(frontier, key=lambda f: -float(f.get("priority", 0))):
                fid = item.get("id", "")
                keep = "\u2713" if item.get("status") != "rejected" else "\u2717"
                table.add_row(fid, str(item.get("priority", "")),
                              item.get("status", ""), item.get("description", "")[:40], keep)
            yield table
            yield Static("[Space] Toggle  [a] Approve all  [Enter] Confirm  [Esc] Skip", id="review-actions")

    def action_toggle_item(self) -> None:
        table: DataTable = self.query_one("#review-table", DataTable)
        if table.cursor_row is not None:
            row_key = list(table.rows)[table.cursor_row]
            cells = table.get_row(row_key)
            fid = str(cells[0])
            current = self._decisions.get(fid, "approved")
            new_status = "rejected" if current == "approved" else "approved"
            self._decisions[fid] = new_status

    def action_approve_all(self) -> None:
        self._decisions.clear()

    def _apply_decisions(self) -> None:
        if not self._decisions:
            return
        graph = self.state.load_graph()
        for item in graph.get("frontier", []):
            fid = item.get("id", "")
            if fid in self._decisions:
                item["status"] = self._decisions[fid]
        self.state.save_graph(graph)
