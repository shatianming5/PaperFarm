"""Tests for Textual TUI components."""

from open_researcher.tui.widgets import (
    ExperimentStatusPanel,
    HotkeyBar,
    IdeaListPanel,
    RecentExperiments,
    StatsBar,
    render_ideas_markdown,
)


def test_stats_bar_colored_output():
    bar = StatsBar()
    state = {
        "total": 7, "keep": 3, "discard": 2, "crash": 1,
        "best_value": 1.47, "primary_metric": "val_loss",
    }
    bar.update_stats(state)
    assert "3K" in bar.stats_text
    assert "2D" in bar.stats_text
    assert "1.47" in bar.stats_text


def test_stats_bar_empty():
    bar = StatsBar()
    bar.update_stats({"total": 0})
    assert "waiting" in bar.stats_text


def test_experiment_status_panel_running():
    panel = ExperimentStatusPanel()
    activity = {
        "status": "running", "detail": "implementing code changes",
        "idea": "idea-003", "updated_at": "2026-03-09T12:00:00",
    }
    panel.update_status(activity, completed=3, total=10)
    assert "RUNNING" in panel.status_text
    assert "idea-003" in panel.status_text
    assert "3" in panel.status_text and "10" in panel.status_text


def test_experiment_status_panel_idle():
    panel = ExperimentStatusPanel()
    panel.update_status(None, completed=0, total=0)
    assert "IDLE" in panel.status_text


def test_experiment_status_panel_baseline():
    panel = ExperimentStatusPanel()
    activity = {"status": "establishing_baseline", "detail": "running baseline"}
    panel.update_status(activity, completed=0, total=5)
    assert "BASELINE" in panel.status_text or "baseline" in panel.status_text


def test_idea_list_panel_renders():
    panel = IdeaListPanel()
    ideas = [
        {"id": "idea-001", "description": "Add dropout", "status": "done",
         "priority": 1, "result": {"metric_value": 1.23, "verdict": "kept"}},
        {"id": "idea-002", "description": "Batch norm", "status": "running",
         "priority": 2, "result": None},
        {"id": "idea-003", "description": "LR warmup", "status": "pending",
         "priority": 3, "result": None},
    ]
    panel.update_ideas(ideas)
    text = panel.ideas_text
    lines = text.strip().split("\n")
    assert len(lines) == 3
    assert "\u25b6" in text
    assert "\u2713" in text
    assert "\u00b7" in text
    assert "idea-001" in text


def test_idea_list_panel_empty():
    panel = IdeaListPanel()
    panel.update_ideas([])
    assert "No projected backlog items" in panel.ideas_text


def test_hotkey_bar_shows_tabs():
    bar = HotkeyBar()
    rendered = bar.render()
    assert "tabs" in str(rendered)


def test_hotkey_bar_includes_quit():
    bar = HotkeyBar()
    rendered = bar.render()
    assert "q" in str(rendered)


def test_recent_experiments_renders():
    widget = RecentExperiments()
    rows = [
        {"status": "keep", "metric_value": "0.85", "description": "baseline"},
        {"status": "discard", "metric_value": "0.80", "description": "exp1"},
    ]
    widget.update_results(rows)
    assert "0.85" in widget.results_text
    assert "0.80" in widget.results_text


def test_recent_experiments_empty():
    widget = RecentExperiments()
    widget.update_results([])
    assert "No experiments" in widget.results_text


def test_render_ideas_markdown_empty():
    result = render_ideas_markdown([])
    assert "No projected backlog items yet" in result
    assert "Projected Backlog" in result


def test_render_ideas_markdown_with_data():
    ideas = [
        {"id": "idea-001", "description": "Add dropout", "category": "regularization",
         "priority": 1, "status": "done",
         "result": {"metric_value": 0.85, "verdict": "kept"}},
        {"id": "idea-002", "description": "Batch norm", "category": "architecture",
         "priority": 2, "status": "running", "result": None},
        {"id": "idea-003", "description": "LR warmup", "category": "training",
         "priority": 3, "status": "pending", "result": None},
    ]
    result = render_ideas_markdown(ideas)
    assert "idea-001" in result
    assert "Add dropout" in result
    assert "0.85" in result
    assert "kept" in result
    assert "running..." in result
    assert "1 pending" in result
    assert "1 running" in result
    assert "1 done" in result
    assert "3 total projected backlog items" in result


def test_render_ideas_markdown_escapes_pipe():
    ideas = [
        {"id": "idea-001", "description": "Use A|B config", "category": "test|cat",
         "priority": 1, "status": "pending", "result": None},
    ]
    result = render_ideas_markdown(ideas)
    assert "A\\|B" in result
    assert "test\\|cat" in result


def test_backlog_rendering_sorts_by_priority_not_id():
    panel = IdeaListPanel()
    ideas = [
        {"id": "idea-010", "description": "Low priority", "status": "pending", "priority": 10, "result": None},
        {"id": "idea-002", "description": "High priority", "status": "pending", "priority": 1, "result": None},
    ]
    panel.update_ideas(ideas)
    lines = panel.ideas_text.splitlines()
    assert "idea-002" in lines[0]

    markdown = render_ideas_markdown(ideas)
    assert markdown.index("idea-002") < markdown.index("idea-010")
