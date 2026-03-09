import json
import tempfile
from pathlib import Path

from open_researcher.results_cmd import load_results, print_results


def test_load_results():
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
            "2026-03-08T10:00:00\ta1b2c3d\taccuracy\t0.850000\t{}\tkeep\tbaseline\n"
        )
        rows = load_results(Path(tmpdir))
        assert len(rows) == 1
        assert rows[0]["status"] == "keep"


def test_load_results_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        research = Path(tmpdir, ".research")
        research.mkdir()
        (research / "results.tsv").write_text(
            "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        )
        rows = load_results(Path(tmpdir))
        assert len(rows) == 0


def test_print_results_with_missing_fields(tmp_path):
    """print_results should not crash when rows have missing fields."""
    research = tmp_path / ".research"
    research.mkdir()
    # Write a TSV with only some columns (missing primary_metric, commit, etc.)
    (research / "results.tsv").write_text(
        "status\tmetric_value\tdescription\n"
        "keep\t0.85\tbaseline\n"
    )
    # Should not crash — missing fields get "<missing>"
    print_results(tmp_path)


def test_print_results_no_experiments(tmp_path, capsys):
    """print_results should print message when no experiments exist."""
    research = tmp_path / ".research"
    research.mkdir()
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
    )
    print_results(tmp_path)
    captured = capsys.readouterr()
    assert "No experiment results" in captured.out


def test_results_json_output(tmp_path, capsys):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08T10:00:00\ta1b\tacc\t0.85\t{}\tkeep\tbaseline\n"
    )
    from open_researcher.results_cmd import print_results_json

    print_results_json(tmp_path)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["status"] == "keep"


def test_results_chart_no_crash(tmp_path):
    """Chart should not crash even with data."""
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(
        "mode: autonomous\nmetrics:\n  primary:\n    name: acc\n    direction: higher_is_better\n"
    )
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
        "2026-03-08\ta1b\tacc\t0.85\t{}\tkeep\tbaseline\n"
        "2026-03-08\ta2b\tacc\t0.87\t{}\tkeep\texp1\n"
        "2026-03-08\ta3b\tacc\t0.83\t{}\tdiscard\texp2\n"
    )
    from open_researcher.results_cmd import print_results_chart

    # Should not raise
    print_results_chart(tmp_path)


def test_results_chart_empty(tmp_path, capsys):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
    )
    from open_researcher.results_cmd import print_results_chart

    print_results_chart(tmp_path)
    captured = capsys.readouterr()
    assert "No results" in captured.out
