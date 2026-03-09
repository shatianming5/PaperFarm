"""Tests for the start command."""

import subprocess
from pathlib import Path


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


def test_do_start_auto_inits(tmp_path):
    """start should auto-create .research/ if it doesn't exist."""
    from open_researcher.start_cmd import do_start_init

    _make_git_repo(tmp_path)
    research = do_start_init(tmp_path, tag="test")
    assert research.is_dir()
    assert (research / "scout_program.md").is_file()
    assert (research / "config.yaml").is_file()


def test_do_start_skips_init_if_exists(tmp_path):
    """start should not re-init if .research/ already exists."""
    from open_researcher.start_cmd import do_start_init

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text("mode: autonomous\n")
    (research / "scout_program.md").write_text("# scout")

    result = do_start_init(tmp_path, tag="test")
    assert result == research
    # Original files should be untouched
    assert (research / "config.yaml").read_text() == "mode: autonomous\n"


def test_render_scout_with_goal(tmp_path):
    """Scout program should include goal when provided."""
    from open_researcher.start_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()

    render_scout_program(research, tag="test", goal="reduce val_loss")
    content = (research / "scout_program.md").read_text()
    assert "reduce val_loss" in content


def test_render_scout_without_goal(tmp_path):
    """Scout program should work without goal."""
    from open_researcher.start_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()

    render_scout_program(research, tag="test", goal=None)
    content = (research / "scout_program.md").read_text()
    assert "Research Goal" not in content
