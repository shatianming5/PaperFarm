"""Tests for bootstrap helpers used by the unified `run` workflow."""

import subprocess
from pathlib import Path


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


def test_bootstrap_init_auto_inits(tmp_path):
    """Bootstrap should auto-create `.research/` when it doesn't exist."""
    from open_researcher.run_cmd import do_start_init

    _make_git_repo(tmp_path)
    research = do_start_init(tmp_path, tag="test")
    assert research.is_dir()
    assert (research / "scout_program.md").is_file()
    assert (research / "config.yaml").is_file()


def test_bootstrap_init_skips_if_exists(tmp_path):
    """Bootstrap should not re-init when `.research/` already exists."""
    from open_researcher.run_cmd import do_start_init

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text("mode: autonomous\n")
    (research / "scout_program.md").write_text("# scout")

    result = do_start_init(tmp_path, tag="test")
    assert result == research
    # Original files should be untouched
    assert (research / "config.yaml").read_text() == "mode: autonomous\n"


def test_render_scout_program_with_goal(tmp_path):
    """Scout program should include goal when provided."""
    from open_researcher.run_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()

    render_scout_program(research, tag="test", goal="reduce val_loss")
    content = (research / "scout_program.md").read_text()
    assert "reduce val_loss" in content


def test_render_scout_program_without_goal(tmp_path):
    """Scout program should work without goal."""
    from open_researcher.run_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()

    render_scout_program(research, tag="test", goal=None)
    content = (research / "scout_program.md").read_text()
    assert "Research Goal" not in content


def test_render_scout_program_prefers_internal_role_file_when_present(tmp_path):
    """Scout render should update internal role file and keep legacy file in sync."""
    from open_researcher.role_programs import internal_role_program_file
    from open_researcher.run_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()
    internal_path = research / internal_role_program_file("scout")
    internal_path.parent.mkdir(parents=True, exist_ok=True)
    internal_path.write_text("# stale\n")

    render_scout_program(research, tag="test", goal="improve f1")

    assert "improve f1" in internal_path.read_text()
    assert "improve f1" in (research / "scout_program.md").read_text()
