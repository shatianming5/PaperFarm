"""TUI renderer for typed research loop events."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from open_researcher.event_journal import EventJournal
from open_researcher.log_output import make_safe_output
from open_researcher.research_events import (
    AgentOutput,
    AllIdeasProcessed,
    ClaimUpdated,
    CrashLimitReached,
    CriticReviewStarted,
    EvidenceRecorded,
    ExperimentCompleted,
    ExperimentPreflightFailed,
    ExperimentSpecCreated,
    ExperimentStarted,
    FrontierSynced,
    HypothesisProposed,
    LimitReached,
    ManagerCycleStarted,
    MemoryUpdated,
    NoPendingIdeas,
    PhaseTransition,
    ReproductionRequested,
    ResearchEvent,
    RoleFailed,
    ScoutStarted,
    SessionFailed,
)

if TYPE_CHECKING:
    from open_researcher.tui.app import ResearchApp


class TUIEventRenderer:
    """Render typed research events into the existing unified TUI log."""

    def __init__(self, app: "ResearchApp", research_dir: Path):
        self._app = app
        self._safe_output = make_safe_output(app.append_log, research_dir / "run.log")
        self._journal = EventJournal(research_dir / "events.jsonl")

    def close(self) -> None:
        if hasattr(self._safe_output, "close"):
            self._safe_output.close()
        self._journal.close()

    def make_output_callback(self, phase: str):
        def on_output(line: str) -> None:
            self.on_event(AgentOutput(phase=phase, detail=line))

        return on_output

    def _set_phase(self, phase: str) -> None:
        try:
            self._app.call_from_thread(setattr, self._app, "app_phase", phase)
        except RuntimeError:
            pass

    @staticmethod
    def _id_suffix(ids: list[str] | None) -> str:
        if not ids:
            return ""
        clean = [item for item in ids if item]
        if not clean:
            return ""
        preview = ", ".join(clean[:2])
        if len(clean) > 2:
            preview = f"{preview}, +{len(clean) - 2}"
        return f" [{preview}]"

    @staticmethod
    def _format_trace_suffix(record: dict | None) -> str:
        if not isinstance(record, dict):
            return ""
        parts: list[str] = []
        for key in [
            "claim_update_id",
            "evidence_id",
            "frontier_id",
            "execution_id",
            "reason_code",
        ]:
            value = str(record.get(key, "")).strip()
            if value:
                parts.append(value)
        if not parts:
            return ""
        return f" [{' / '.join(parts)}]"

    def _first_item_suffix(self, items: list[dict] | None) -> str:
        if not items:
            return ""
        for item in items:
            suffix = self._format_trace_suffix(item if isinstance(item, dict) else None)
            if suffix:
                return suffix
        return ""

    def _experiment_suffix(self, event: ExperimentStarted | ExperimentCompleted) -> str:
        return self._format_trace_suffix(
            {
                "frontier_id": event.frontier_id,
                "execution_id": event.execution_id,
                "reason_code": event.selection_reason_code,
            }
        )

    def on_event(self, event: ResearchEvent) -> None:
        self._journal.emit_typed(event)

        if isinstance(event, AgentOutput):
            self._safe_output(event.detail)
            return

        if isinstance(event, ScoutStarted):
            self._set_phase("scouting")
            return

        if isinstance(event, ManagerCycleStarted):
            self._set_phase("experimenting")
            self._safe_output(f"[system] === Graph cycle {event.cycle}: Starting Research Manager ===")
            return

        if isinstance(event, HypothesisProposed):
            self._safe_output(
                f"[manager] Proposed/updated {event.count} hypothesis item(s)."
                f"{self._id_suffix(event.hypothesis_ids)}"
            )
            return

        if isinstance(event, ExperimentSpecCreated):
            self._safe_output(
                f"[manager] Prepared {event.count} experiment spec(s)."
                f"{self._id_suffix(event.experiment_spec_ids)}"
            )
            return

        if isinstance(event, CriticReviewStarted):
            self._safe_output(f"[critic] Starting {event.stage} review.")
            return

        if isinstance(event, FrontierSynced):
            self._safe_output(
                f"[system] Frontier synced ({event.frontier_items} runnable item(s))."
                f"{self._first_item_suffix(event.items)}"
            )
            return

        if isinstance(event, ExperimentPreflightFailed):
            self._safe_output(
                f"[critic] Rejected {event.rejected_count} experiment spec(s)."
                f"{self._first_item_suffix(event.items)}"
            )
            return

        if isinstance(event, ExperimentStarted):
            self._set_phase("experimenting")
            self._safe_output(
                f"[exp] Starting experiment agent (run #{event.experiment_num})..."
                f"{self._experiment_suffix(event)}"
            )
            return

        if isinstance(event, ExperimentCompleted):
            self._safe_output(
                f"[exp] Experiment agent finished (run #{event.experiment_num}, code={event.exit_code})."
                f"{self._experiment_suffix(event)}"
            )
            return

        if isinstance(event, RoleFailed):
            self._safe_output(f"[system] {event.role} failed with exit code {event.exit_code}.")
            return

        if isinstance(event, NoPendingIdeas):
            self._safe_output("[system] No projected backlog items remain. Stopping.")
            return

        if isinstance(event, EvidenceRecorded):
            self._safe_output(
                f"[critic] Recorded {event.evidence_created} evidence item(s)."
                f"{self._first_item_suffix(event.items)}"
            )
            return

        if isinstance(event, ClaimUpdated):
            self._safe_output(
                f"[critic] Updated {event.count} claim(s)."
                f"{self._first_item_suffix(event.items)}"
            )
            return

        if isinstance(event, ReproductionRequested):
            self._safe_output(
                f"[critic] Requested reproduction for {event.count} item(s)."
                f"{self._first_item_suffix(event.items)}"
            )
            return

        if isinstance(event, MemoryUpdated):
            self._safe_output(
                f"[system] Memory updated (ideation={event.ideation_memory}, experiment={event.experiment_memory})."
            )
            return

        if isinstance(event, LimitReached):
            self._safe_output(f"[system] Max experiments ({event.max_experiments}) reached. Stopping.")
            return

        if isinstance(event, CrashLimitReached):
            self._safe_output(
                f"[system] Crash limit reached ({event.max_crashes} consecutive crashes). Pausing."
            )
            return

        if isinstance(event, PhaseTransition):
            self._safe_output(f"[system] Phase transition to '{event.next_phase}' — pausing for review.")
            return

        if isinstance(event, AllIdeasProcessed):
            self._safe_output("[system] All cycles finished.")
            return

        if isinstance(event, SessionFailed):
            self._safe_output(
                f"[system] Session failed while running {event.failed_role} (code={event.exit_code})."
            )
