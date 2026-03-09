"""Phase gate -- pause for human review in collaborative mode."""

import json
from pathlib import Path

from filelock import FileLock

from open_researcher.storage import atomic_write_json


class PhaseGate:
    def __init__(self, research_dir: Path, mode: str = "autonomous"):
        self.research_dir = research_dir
        self.mode = mode
        self._last_phase = self._read_phase()

    def _read_phase(self) -> str:
        path = self.research_dir / "experiment_progress.json"
        if not path.exists():
            return "init"
        try:
            return json.loads(path.read_text()).get("phase", "init")
        except (json.JSONDecodeError, OSError):
            return "init"

    def check(self) -> str | None:
        """Check for phase transition. Returns new phase if paused, else None."""
        current = self._read_phase()
        if current != self._last_phase:
            self._last_phase = current
            if self.mode == "collaborative":
                self._pause(current)
                return current
        return None

    def _pause(self, phase: str) -> None:
        ctrl_path = self.research_dir / "control.json"
        lock = FileLock(str(ctrl_path) + ".lock")
        reason = f"Phase completed: {phase}"
        with lock:
            try:
                ctrl = json.loads(ctrl_path.read_text())
            except (json.JSONDecodeError, OSError):
                ctrl = {}
            ctrl["paused"] = True
            ctrl["pause_reason"] = reason
            atomic_write_json(ctrl_path, ctrl)
