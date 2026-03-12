"""Tests for internal role program file helpers."""

from __future__ import annotations

from pathlib import Path

from open_researcher.role_programs import (
    ensure_internal_role_programs,
    ensure_legacy_role_programs,
    internal_role_program_file,
    legacy_role_program_file,
    missing_role_programs,
    render_scout_program,
    resolve_role_program_file,
)


def test_ensure_internal_role_programs_renders_templates_with_context(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()

    ensure_internal_role_programs(research, context={"tag": "demo"})

    scout_path = research / internal_role_program_file("scout")
    manager_path = research / internal_role_program_file("manager")
    critic_path = research / internal_role_program_file("critic")
    exp_path = research / internal_role_program_file("experiment")
    assert scout_path.exists()
    assert manager_path.exists()
    assert critic_path.exists()
    assert exp_path.exists()
    assert "research/demo" in exp_path.read_text(encoding="utf-8")


def test_ensure_internal_role_programs_migrates_from_legacy_files(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()

    legacy = research / legacy_role_program_file("manager")
    legacy.write_text("# legacy-manager\n", encoding="utf-8")

    ensure_internal_role_programs(research)

    internal = research / internal_role_program_file("manager")
    assert internal.read_text(encoding="utf-8") == "# legacy-manager\n"


def test_resolve_role_program_file_prefers_internal_then_legacy(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()

    assert resolve_role_program_file(research, "manager") == internal_role_program_file("manager")

    legacy = research / legacy_role_program_file("manager")
    legacy.write_text("# legacy\n", encoding="utf-8")
    assert resolve_role_program_file(research, "manager") == legacy_role_program_file("manager")

    internal = research / internal_role_program_file("manager")
    internal.parent.mkdir(parents=True, exist_ok=True)
    internal.write_text("# internal\n", encoding="utf-8")
    assert resolve_role_program_file(research, "manager") == internal_role_program_file("manager")


def test_resolve_role_program_file_supports_scout_role(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()

    assert resolve_role_program_file(research, "scout") == internal_role_program_file("scout")

    legacy = research / legacy_role_program_file("scout")
    legacy.write_text("# legacy-scout\n", encoding="utf-8")
    assert resolve_role_program_file(research, "scout") == legacy_role_program_file("scout")

    internal = research / internal_role_program_file("scout")
    internal.parent.mkdir(parents=True, exist_ok=True)
    internal.write_text("# internal-scout\n", encoding="utf-8")
    assert resolve_role_program_file(research, "scout") == internal_role_program_file("scout")


def test_missing_role_programs_reports_unavailable_roles(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()

    # Only manager is present through legacy file.
    (research / legacy_role_program_file("manager")).write_text("# manager\n", encoding="utf-8")

    missing = missing_role_programs(research)
    assert missing == ["scout", "critic", "experiment"]


def test_ensure_legacy_role_programs_copies_internal_content(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()
    internal = research / internal_role_program_file("scout")
    internal.parent.mkdir(parents=True, exist_ok=True)
    internal.write_text("# internal scout\n", encoding="utf-8")

    ensure_legacy_role_programs(research, ["scout"])

    legacy = research / legacy_role_program_file("scout")
    assert legacy.read_text(encoding="utf-8") == "# internal scout\n"


def test_render_scout_program_writes_resolved_and_legacy_paths(tmp_path: Path):
    research = tmp_path / ".research"
    research.mkdir()
    internal = research / internal_role_program_file("scout")
    internal.parent.mkdir(parents=True, exist_ok=True)
    internal.write_text("# stale scout\n", encoding="utf-8")

    resolved = render_scout_program(research, tag="demo", goal="improve f1")

    assert resolved == internal_role_program_file("scout")
    assert "improve f1" in internal.read_text(encoding="utf-8")
    assert "improve f1" in (research / legacy_role_program_file("scout")).read_text(encoding="utf-8")
