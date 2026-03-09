"""Tests for app state machine."""

import json
import tempfile
from pathlib import Path


def test_app_state_default():
    """ResearchApp should default to EXPERIMENTING state."""
    from open_researcher.tui.app import ResearchApp

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = tmp_path / ".research"
        research.mkdir()
        (research / "idea_pool.json").write_text('{"ideas": []}')
        (research / "activity.json").write_text('{}')

        app = ResearchApp(tmp_path)
        assert app.app_phase == "experimenting"


def test_app_state_scouting():
    """ResearchApp should support scouting state."""
    from open_researcher.tui.app import ResearchApp

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = tmp_path / ".research"
        research.mkdir()
        (research / "idea_pool.json").write_text('{"ideas": []}')
        (research / "activity.json").write_text('{}')

        app = ResearchApp(tmp_path, initial_phase="scouting")
        assert app.app_phase == "scouting"
