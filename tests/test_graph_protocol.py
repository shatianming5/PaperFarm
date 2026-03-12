"""Tests for graph protocol artifact backfill helpers."""

from __future__ import annotations

from open_researcher.graph_protocol import ensure_graph_protocol_artifacts
from open_researcher.role_programs import internal_role_program_file, legacy_role_program_file


def test_ensure_graph_protocol_artifacts_backfills_legacy_scout_from_internal(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()

    internal_scout = research / internal_role_program_file("scout")
    internal_scout.parent.mkdir(parents=True, exist_ok=True)
    internal_scout.write_text("# internal scout\n", encoding="utf-8")

    ensure_graph_protocol_artifacts(research)

    legacy_scout = research / legacy_role_program_file("scout")
    assert legacy_scout.exists()
    assert legacy_scout.read_text(encoding="utf-8") == "# internal scout\n"


def test_ensure_graph_protocol_artifacts_creates_scout_files_when_missing(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()

    ensure_graph_protocol_artifacts(research)

    internal_scout = research / internal_role_program_file("scout")
    legacy_scout = research / legacy_role_program_file("scout")
    assert internal_scout.exists()
    assert legacy_scout.exists()
    assert "Scout Program" in internal_scout.read_text(encoding="utf-8")
    assert legacy_scout.read_text(encoding="utf-8") == internal_scout.read_text(encoding="utf-8")
