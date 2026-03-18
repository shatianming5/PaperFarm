"""Result review modal -- shown at end of round."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Label, Static, TextArea

from .base import ReviewScreen


class ResultReviewScreen(ReviewScreen):
    """Review experiment results and optionally override AI keep/discard decisions."""

    BINDINGS = [
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "skip", "Skip"),
        Binding("space", "toggle_override", "Override"),
    ]

    def __init__(self, state, review_request, **kwargs):
        super().__init__(state=state, review_request=review_request, **kwargs)
        self._overrides: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        results = self.state.load_results()
        config = self.state.load_config()
        baseline_name = config.get("metrics", {}).get("primary", {}).get("name", "metric")

        with Vertical(id="review-dialog"):
            yield Label("Round Results", id="review-title")
            table = DataTable(id="result-table")
            table.add_columns("Frontier", "Value", "AI Decision", "Override?")
            table.cursor_type = "row"
            for r in results[-10:]:
                fid = r.get("frontier_id", "")
                val = r.get("value", "")
                status = r.get("status", "")
                table.add_row(fid, str(val), status, "\u2014")
            yield table
            yield Label("\nConstraints for next round:")
            yield TextArea(id="next-constraints")
            yield Static("[Space] Override  [Enter] Next round  [Esc] Skip", id="review-actions")

    def action_toggle_override(self) -> None:
        table: DataTable = self.query_one("#result-table", DataTable)
        if table.cursor_row is not None:
            row_key = list(table.rows)[table.cursor_row]
            cells = table.get_row(row_key)
            fid = str(cells[0])
            ai_status = str(cells[2])
            new = "keep" if ai_status == "discard" else "discard"
            self._overrides[fid] = new

    def _apply_decisions(self) -> None:
        if self._overrides:
            graph = self.state.load_graph()
            for fid, new_status in self._overrides.items():
                graph.setdefault("claim_updates", []).append({
                    "frontier_id": fid,
                    "new_status": new_status,
                    "reviewer": "human",
                })
                self.state.append_log({
                    "event": "human_override",
                    "frontier_id": fid,
                    "new_status": new_status,
                })
            self.state.save_graph(graph)

        try:
            textarea = self.query_one("#next-constraints", TextArea)
            text = textarea.text.strip()
            if text:
                path = self.state.dir / "user_constraints.md"
                with open(path, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
                self.state.append_log({"event": "goal_updated"})
        except Exception:
            pass
