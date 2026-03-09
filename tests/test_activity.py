"""Tests for activity monitor."""


import pytest

from open_researcher.activity import ActivityMonitor


@pytest.fixture
def research_dir(tmp_path):
    d = tmp_path / ".research"
    d.mkdir()
    return d


@pytest.fixture
def monitor(research_dir):
    return ActivityMonitor(research_dir)


def test_update_and_get(monitor, research_dir):
    monitor.update("idea_agent", status="analyzing", detail="reviewing #7")
    activity = monitor.get("idea_agent")
    assert activity["status"] == "analyzing"
    assert activity["detail"] == "reviewing #7"
    assert "updated_at" in activity


def test_get_missing_agent(monitor):
    assert monitor.get("nonexistent") is None


def test_update_experiment_agent(monitor):
    monitor.update(
        "experiment_agent",
        status="evaluating",
        idea="cosine LR",
        experiment=8,
        gpu={"host": "local", "device": 0},
        branch="exp/cosine-lr",
    )
    act = monitor.get("experiment_agent")
    assert act["status"] == "evaluating"
    assert act["gpu"]["device"] == 0


def test_get_all(monitor):
    monitor.update("idea_agent", status="idle")
    monitor.update("experiment_agent", status="coding")
    all_act = monitor.get_all()
    assert "idea_agent" in all_act
    assert "experiment_agent" in all_act


def test_update_worker(tmp_path):
    from open_researcher.activity import ActivityMonitor
    am = ActivityMonitor(tmp_path)
    am.update_worker("experiment_master", "w-001", status="coding", idea="idea-001", gpus=[0])
    data = am.get("experiment_master")
    assert "workers" in data
    assert len(data["workers"]) == 1
    assert data["workers"][0]["id"] == "w-001"
    assert data["workers"][0]["status"] == "coding"


def test_update_worker_multiple(tmp_path):
    from open_researcher.activity import ActivityMonitor
    am = ActivityMonitor(tmp_path)
    am.update_worker("experiment_master", "w-001", status="coding", idea="idea-001", gpus=[0])
    am.update_worker("experiment_master", "w-002", status="evaluating", idea="idea-002", gpus=[1, 2])
    data = am.get("experiment_master")
    assert len(data["workers"]) == 2


def test_remove_worker(tmp_path):
    from open_researcher.activity import ActivityMonitor
    am = ActivityMonitor(tmp_path)
    am.update_worker("experiment_master", "w-001", status="coding", idea="idea-001", gpus=[0])
    am.remove_worker("experiment_master", "w-001")
    data = am.get("experiment_master")
    assert len(data["workers"]) == 0
