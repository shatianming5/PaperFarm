"""Tests for config reader."""

import pytest
import yaml

from open_researcher.config import ResearchConfig, load_config


@pytest.fixture
def research_dir(tmp_path):
    d = tmp_path / ".research"
    d.mkdir()
    return d


def test_load_config(research_dir):
    """Load config with all fields specified."""
    config_data = {
        "mode": "collaborative",
        "experiment": {
            "timeout": 1200,
            "max_consecutive_crashes": 5,
            "max_parallel_workers": 4,
            "worker_agent": "claude-code",
        },
        "metrics": {
            "primary": {
                "name": "accuracy",
                "direction": "maximize",
            },
        },
        "gpu": {
            "remote_hosts": ["host1:8080", "host2:8080"],
        },
        "research": {
            "web_search": False,
            "search_interval": 10,
        },
    }
    config_path = research_dir / "config.yaml"
    config_path.write_text(yaml.dump(config_data))

    cfg = load_config(research_dir)

    assert cfg.mode == "collaborative"
    assert cfg.timeout == 1200
    assert cfg.max_crashes == 5
    assert cfg.max_workers == 4
    assert cfg.worker_agent == "claude-code"
    assert cfg.primary_metric == "accuracy"
    assert cfg.direction == "maximize"
    assert cfg.web_search is False
    assert cfg.search_interval == 10
    assert cfg.remote_hosts == ["host1:8080", "host2:8080"]


def test_load_config_defaults(research_dir):
    """Load config with minimal content -- all defaults should apply."""
    config_path = research_dir / "config.yaml"
    config_path.write_text(yaml.dump({"mode": "autonomous"}))

    cfg = load_config(research_dir)

    assert cfg.mode == "autonomous"
    assert cfg.timeout == 600
    assert cfg.max_crashes == 3
    assert cfg.max_workers == 0
    assert cfg.worker_agent == ""
    assert cfg.primary_metric == ""
    assert cfg.direction == ""
    assert cfg.web_search is True
    assert cfg.search_interval == 5
    assert cfg.remote_hosts == []


def test_load_config_missing_file(research_dir):
    """When config.yaml does not exist, return all defaults."""
    cfg = load_config(research_dir)

    assert isinstance(cfg, ResearchConfig)
    assert cfg.mode == "autonomous"
    assert cfg.timeout == 600
    assert cfg.max_crashes == 3
    assert cfg.max_workers == 0
    assert cfg.worker_agent == ""
    assert cfg.primary_metric == ""
    assert cfg.direction == ""
    assert cfg.web_search is True
    assert cfg.search_interval == 5
    assert cfg.remote_hosts == []
