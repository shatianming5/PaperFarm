import json
import tempfile
from pathlib import Path

from open_researcher.status_cmd import parse_research_state, print_status


def test_parse_state_with_results():
    """Should correctly parse results.tsv and config.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: autonomous\nmetrics:\n  primary:\n    name: accuracy\n    direction: higher_is_better\n"
        )

        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
            "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
            "2026-03-08T10:15:00\tb2c3d4e\taccuracy\t0.872000\t{}\tkeep\tincrease LR\n"
            "2026-03-08T10:30:00\tc3d4e5f\taccuracy\t0.840000\t{}\tdiscard\tswitch optimizer\n"
            "2026-03-08T10:45:00\td4e5f6g\taccuracy\t0.000000\t{}\tcrash\tOOM\n"
        )

        # Write filled project understanding
        (research / "project-understanding.md").write_text("# Project\n\nThis is a real project description.")

        # Write filled literature review
        (research / "literature.md").write_text("# Literature Review\n\nFound relevant papers on optimization.")

        # Write filled evaluation
        (research / "evaluation.md").write_text("# Eval\n\nThis uses accuracy as the metric.")

        state = parse_research_state(Path(tmpdir))

        assert state["mode"] == "autonomous"
        assert state["primary_metric"] == "accuracy"
        assert state["direction"] == "higher_is_better"
        assert state["total"] == 4
        assert state["keep"] == 2
        assert state["discard"] == 1
        assert state["crash"] == 1
        assert state["baseline_value"] == 0.85
        assert state["current_value"] == 0.872
        assert state["best_value"] == 0.872
        assert len(state["recent"]) == 4


def test_parse_state_empty():
    """Should handle empty results.tsv (no experiments yet)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: collaborative\nmetrics:\n  primary:\n    name: ''\n    direction: ''\n"
        )
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        )
        (research / "project-understanding.md").write_text("<!-- empty -->")
        (research / "evaluation.md").write_text("<!-- empty -->")

        state = parse_research_state(Path(tmpdir))
        assert state["total"] == 0
        assert state["phase"] == 1  # project understanding not filled


def test_detect_phase_2_literature():
    """Phase 2 when project-understanding has content but literature doesn't."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: autonomous\nmetrics:\n  primary:\n    name: ''\n    direction: ''\n"
        )
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        )
        # Filled project understanding
        (research / "project-understanding.md").write_text("# Project\n\nThis is a real project description.")
        # Empty literature review
        (research / "literature.md").write_text("<!-- empty -->")
        (research / "evaluation.md").write_text("<!-- empty -->")

        state = parse_research_state(Path(tmpdir))
        assert state["phase"] == 2  # literature not filled


def test_detect_phase_3_evaluation():
    """Phase 3 when literature has content but evaluation doesn't."""
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()

        (research / "config.yaml").write_text(
            "mode: autonomous\nmetrics:\n  primary:\n    name: ''\n    direction: ''\n"
        )
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        )
        (research / "project-understanding.md").write_text("# Project\n\nThis is a real project description.")
        (research / "literature.md").write_text("# Literature Review\n\nFound relevant papers on optimization.")
        (research / "evaluation.md").write_text("<!-- empty -->")

        state = parse_research_state(Path(tmpdir))
        assert state["phase"] == 3  # evaluation not filled


def test_print_status_english_output(capsys):
    """Verify status output uses English, not Chinese."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        research = repo / ".research"
        research.mkdir()
        config = "mode: autonomous\nmetrics:\n  primary:\n    name: accuracy\n    direction: higher_is_better\n"
        (research / "config.yaml").write_text(config)
        header = "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        (research / "results.tsv").write_text(header)
        (research / "project-understanding.md").write_text("<!-- placeholder -->\n")
        (research / "evaluation.md").write_text("<!-- placeholder -->\n")
        print_status(repo)
        captured = capsys.readouterr()
        assert "Phase 1" in captured.out
        assert "阶段" not in captured.out
        assert "分支" not in captured.out
        assert "模式" not in captured.out
        assert "实验统计" not in captured.out


def test_status_shows_activity(tmp_path):
    """Status should not crash when activity.json exists."""
    research = tmp_path / ".research"
    research.mkdir()
    # Minimal config
    config_text = "mode: autonomous\nmetrics:\n  primary:\n    name: acc\n    direction: higher_is_better\n"
    (research / "config.yaml").write_text(config_text)
    header = "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
    (research / "results.tsv").write_text(header)
    (research / "activity.json").write_text(
        json.dumps(
            {"idea_agent": {"status": "analyzing", "detail": "reviewing #3", "updated_at": "2026-03-09T15:00:00Z"}}
        )
    )
    # Create the docs files as empty
    for name in ["project-understanding.md", "literature.md", "evaluation.md"]:
        (research / name).write_text("# placeholder\n")
    from open_researcher.status_cmd import parse_research_state

    state = parse_research_state(tmp_path)
    assert state is not None
    assert state["total"] == 0
