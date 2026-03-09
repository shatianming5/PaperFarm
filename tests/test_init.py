import json
import os
import subprocess
import tempfile
from pathlib import Path

from open_researcher.init_cmd import do_init


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


def test_init_creates_shared_files(tmp_path):
    """Verify init creates idea_pool.json, activity.json, control.json."""
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


def test_worker_prompt_template_renders():
    from jinja2 import Environment, PackageLoader
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("worker_prompt.md.j2")
    result = tmpl.render(
        idea_id="idea-003",
        idea_description="Use cosine annealing with warmup",
        gpu_devices="0,1",
        gpu_count=2,
        worktree_path="/tmp/worktree-003",
        evaluation_content="# Eval\nRun train.py",
        config_content="mode: autonomous",
        tag="demo",
    )
    assert "idea-003" in result
    assert "cosine annealing" in result
    assert "CUDA_VISIBLE_DEVICES=0,1" in result
    assert "torchrun" in result


def test_experiment_program_master_mode():
    from jinja2 import Environment, PackageLoader
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("experiment_program.md.j2")
    result = tmpl.render(tag="demo")
    assert "Master" in result or "master" in result
    assert "sub-agent" in result or "worker" in result
    assert "git worktree" in result
    assert "CUDA_VISIBLE_DEVICES" in result
