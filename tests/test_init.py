import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from open_researcher.init_cmd import do_init


@pytest.fixture
def init_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    do_init(repo_path=tmp_path, tag="test")
    return tmp_path / ".research"


def test_init_creates_research_directory():
    """init should create .research/ with all expected files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)

        do_init(repo_path=Path(tmpdir), tag="test1")

        research = Path(tmpdir, ".research")
        assert research.is_dir()
        assert (research / "program.md").is_file()
        assert (research / "config.yaml").is_file()
        assert (research / "project-understanding.md").is_file()
        assert (research / "evaluation.md").is_file()
        assert (research / "literature.md").is_file()
        assert (research / "ideas.md").is_file()
        assert (research / "results.tsv").is_file()
        assert (research / "scripts" / "record.py").is_file()
        assert (research / "scripts" / "rollback.sh").is_file()

        # Check tag substitution in program.md
        program = (research / "program.md").read_text()
        assert "test1" in program

        # Check results.tsv has header
        results = (research / "results.tsv").read_text()
        assert results.startswith("timestamp\t")

        # Check rollback.sh is executable
        assert os.access(research / "scripts" / "rollback.sh", os.X_OK)


def test_init_refuses_if_research_exists():
    """init should refuse if .research/ already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        Path(tmpdir, ".research").mkdir()

        try:
            do_init(repo_path=Path(tmpdir), tag="test2")
            assert False, "Should have raised"
        except SystemExit:
            pass


def test_init_generates_default_tag():
    """init without tag should use today's date."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir, capture_output=True)

        do_init(repo_path=Path(tmpdir), tag=None)

        program = (Path(tmpdir) / ".research" / "program.md").read_text()
        assert "research/" in program


def test_init_fails_without_git_directory(tmp_path):
    """init should fail if .git directory does not exist."""
    with pytest.raises(SystemExit):
        do_init(repo_path=tmp_path, tag="test-nogit")
    # .research should NOT have been created
    assert not (tmp_path / ".research").exists()


def test_init_creates_shared_files(tmp_path):
    """Verify init creates idea_pool.json, activity.json, control.json."""
    # Need .git for the new validation
    (tmp_path / ".git").mkdir()
    do_init(repo_path=tmp_path, tag="test")
    research = tmp_path / ".research"

    pool = research / "idea_pool.json"
    assert pool.exists()
    data = json.loads(pool.read_text())
    assert data == {"ideas": []}

    activity = research / "activity.json"
    assert activity.exists()

    control = research / "control.json"
    assert control.exists()
    data = json.loads(control.read_text())
    assert data == {"paused": False, "skip_current": False}

    # Multi-agent templates rendered
    assert (research / "idea_program.md").exists()
    assert (research / "experiment_program.md").exists()


def test_experiment_program_serial_mode():
    from jinja2 import Environment, PackageLoader

    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("experiment_program.md.j2")
    result = tmpl.render(tag="demo")
    assert "Serial Experiment Runner" in result
    assert "one at a time" in result
    assert "experiment_progress.json" in result
    assert "research/demo" in result


def test_init_creates_experiment_progress(init_dir):
    """init should create experiment_progress.json with phase=init."""
    progress = init_dir / "experiment_progress.json"
    assert progress.exists()
    data = json.loads(progress.read_text())
    assert data == {"phase": "init"}


def test_init_creates_gpu_status_file(init_dir):
    """init should create gpu_status.json."""
    gpu_file = init_dir / "gpu_status.json"
    assert gpu_file.exists()
    data = json.loads(gpu_file.read_text())
    assert "gpus" in data


def test_init_creates_worktrees_dir(init_dir):
    """init should create .research/worktrees/ directory."""
    worktrees = init_dir / "worktrees"
    assert worktrees.is_dir()
