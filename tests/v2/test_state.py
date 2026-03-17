"""Comprehensive tests for open_researcher_v2.state.ResearchState."""

from __future__ import annotations

import json

import yaml
import pytest

from open_researcher_v2.state import (
    ResearchState,
    _DEFAULT_CONFIG,
    _DEFAULT_ACTIVITY,
    _RESULTS_FIELDS,
    _deep_merge,
    _default_graph,
)


# ---------------------------------------------------------------------------
# TestConfig
# ---------------------------------------------------------------------------


class TestConfig:
    """Tests for config.yaml loading with defaults merging."""

    def test_load_default_when_missing(self, tmp_path):
        """When no config.yaml exists, defaults are returned."""
        state = ResearchState(tmp_path)
        cfg = state.load_config()
        assert cfg["protocol"] == "research-v1"
        assert cfg["metrics"]["primary"]["name"] == ""
        assert cfg["workers"]["timeout"] == 600
        assert cfg["limits"]["max_crashes"] == 3
        assert cfg["agent"]["web_search"] is True

    def test_load_existing_merges_with_defaults(self, tmp_path):
        """User config is deep-merged over defaults."""
        user_cfg = {
            "protocol": "custom-v2",
            "metrics": {"primary": {"name": "accuracy", "direction": "higher_is_better"}},
            "workers": {"max_parallel": 4},
        }
        (tmp_path / "config.yaml").write_text(
            yaml.dump(user_cfg), encoding="utf-8",
        )
        state = ResearchState(tmp_path)
        cfg = state.load_config()
        # Overridden values
        assert cfg["protocol"] == "custom-v2"
        assert cfg["metrics"]["primary"]["name"] == "accuracy"
        assert cfg["metrics"]["primary"]["direction"] == "higher_is_better"
        assert cfg["workers"]["max_parallel"] == 4
        # Defaults preserved where not overridden
        assert cfg["workers"]["timeout"] == 600
        assert cfg["limits"]["token_budget"] == 0
        assert cfg["agent"]["worker_agent"] == ""

    def test_load_corrupt_yaml_returns_defaults(self, tmp_path):
        """Corrupt YAML returns defaults instead of crashing."""
        (tmp_path / "config.yaml").write_text(
            "{{invalid yaml::", encoding="utf-8",
        )
        state = ResearchState(tmp_path)
        cfg = state.load_config()
        assert cfg["protocol"] == "research-v1"

    def test_load_non_dict_yaml_returns_defaults(self, tmp_path):
        """If YAML parses to a non-dict, return defaults."""
        (tmp_path / "config.yaml").write_text(
            "- just\n- a\n- list\n", encoding="utf-8",
        )
        state = ResearchState(tmp_path)
        cfg = state.load_config()
        assert cfg["protocol"] == "research-v1"


# ---------------------------------------------------------------------------
# TestGraph
# ---------------------------------------------------------------------------


class TestGraph:
    """Tests for graph.json read/write with FileLock."""

    def test_load_default_when_missing(self, tmp_path):
        """Missing graph.json returns the default graph structure."""
        state = ResearchState(tmp_path)
        graph = state.load_graph()
        assert graph["version"] == "research-v1"
        assert graph["hypotheses"] == []
        assert graph["counters"]["hypothesis"] == 0
        assert graph["repo_profile"]["profile_key"] == "general_code"

    def test_save_and_load_roundtrip(self, tmp_path):
        """Graph data survives a save -> load cycle."""
        state = ResearchState(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        graph = _default_graph()
        graph["hypotheses"].append({"id": "h1", "text": "test hypothesis"})
        graph["counters"]["hypothesis"] = 1
        state.save_graph(graph)

        loaded = state.load_graph()
        assert len(loaded["hypotheses"]) == 1
        assert loaded["hypotheses"][0]["id"] == "h1"
        assert loaded["counters"]["hypothesis"] == 1

    def test_load_corrupt_json_returns_default(self, tmp_path):
        """Corrupt graph.json returns default instead of raising."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "graph.json").write_text("not json", encoding="utf-8")
        state = ResearchState(tmp_path)
        graph = state.load_graph()
        assert graph["version"] == "research-v1"

    def test_load_non_dict_json_returns_default(self, tmp_path):
        """A JSON array in graph.json returns default graph."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "graph.json").write_text("[1,2,3]", encoding="utf-8")
        state = ResearchState(tmp_path)
        graph = state.load_graph()
        assert graph["version"] == "research-v1"


# ---------------------------------------------------------------------------
# TestResults
# ---------------------------------------------------------------------------


class TestResults:
    """Tests for results.tsv append and read."""

    def test_empty_when_missing(self, tmp_path):
        """No results.tsv means empty list."""
        state = ResearchState(tmp_path)
        assert state.load_results() == []

    def test_append_and_load(self, tmp_path):
        """Appending a row creates the file with header and data."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        state.append_result({
            "worker": "w0",
            "frontier_id": "f1",
            "status": "keep",
            "metric": "accuracy",
            "value": "0.95",
            "description": "baseline run",
        })
        rows = state.load_results()
        assert len(rows) == 1
        assert rows[0]["worker"] == "w0"
        assert rows[0]["status"] == "keep"
        assert rows[0]["value"] == "0.95"
        # timestamp should be auto-filled
        assert rows[0]["timestamp"] != ""

    def test_append_multiple(self, tmp_path):
        """Multiple appends accumulate rows correctly."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        for i in range(5):
            state.append_result({
                "worker": f"w{i}",
                "frontier_id": f"f{i}",
                "status": "keep" if i % 2 == 0 else "discard",
                "metric": "loss",
                "value": str(float(i) / 10),
                "description": f"exp {i}",
            })
        rows = state.load_results()
        assert len(rows) == 5
        assert rows[0]["worker"] == "w0"
        assert rows[4]["worker"] == "w4"
        assert rows[1]["status"] == "discard"
        assert rows[2]["status"] == "keep"

    def test_append_with_explicit_timestamp(self, tmp_path):
        """An explicit timestamp is preserved."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        state.append_result({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "worker": "w0",
            "status": "keep",
        })
        rows = state.load_results()
        assert rows[0]["timestamp"] == "2026-01-01T00:00:00+00:00"

    def test_load_empty_file(self, tmp_path):
        """An empty file returns empty list."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "results.tsv").write_text("", encoding="utf-8")
        state = ResearchState(tmp_path)
        assert state.load_results() == []


# ---------------------------------------------------------------------------
# TestActivity
# ---------------------------------------------------------------------------


class TestActivity:
    """Tests for activity.json with FileLock."""

    def test_default_when_missing(self, tmp_path):
        """Missing activity.json returns sensible defaults."""
        state = ResearchState(tmp_path)
        act = state.load_activity()
        assert act["phase"] == "idle"
        assert act["paused"] is False
        assert act["skip_current"] is False
        assert act["workers"] == {}

    def test_update_phase(self, tmp_path):
        """update_phase changes the phase field."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        state.update_phase("running")
        act = state.load_activity()
        assert act["phase"] == "running"
        assert act["updated_at"] != ""

    def test_update_worker(self, tmp_path):
        """update_worker inserts and updates worker entries."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        state.update_worker("w0", status="running", experiment="exp1")
        act = state.load_activity()
        assert "w0" in act["workers"]
        assert act["workers"]["w0"]["status"] == "running"
        assert act["workers"]["w0"]["experiment"] == "exp1"

        # Update the same worker
        state.update_worker("w0", status="done")
        act = state.load_activity()
        assert act["workers"]["w0"]["status"] == "done"
        # Previous fields are preserved
        assert act["workers"]["w0"]["experiment"] == "exp1"

    def test_pause_resume(self, tmp_path):
        """set_paused toggles the paused flag."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        assert state.load_activity()["paused"] is False

        state.set_paused(True)
        assert state.load_activity()["paused"] is True

        state.set_paused(False)
        assert state.load_activity()["paused"] is False

    def test_consume_skip(self, tmp_path):
        """consume_skip returns True and resets the flag."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)

        # No skip set: should return False
        assert state.consume_skip() is False

        # Set skip, then consume
        state.set_skip_current(True)
        assert state.load_activity()["skip_current"] is True
        assert state.consume_skip() is True
        assert state.load_activity()["skip_current"] is False

        # Consuming again returns False
        assert state.consume_skip() is False

    def test_load_corrupt_activity(self, tmp_path):
        """Corrupt activity.json returns defaults."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "activity.json").write_text("{bad json", encoding="utf-8")
        state = ResearchState(tmp_path)
        act = state.load_activity()
        assert act["phase"] == "idle"


# ---------------------------------------------------------------------------
# TestLog
# ---------------------------------------------------------------------------


class TestLog:
    """Tests for log.jsonl append and tail."""

    def test_empty_when_missing(self, tmp_path):
        """Missing log.jsonl returns empty list."""
        state = ResearchState(tmp_path)
        assert state.tail_log() == []

    def test_append_and_tail(self, tmp_path):
        """Appended entries can be read back via tail."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        state.append_log({"event": "start", "worker": "w0"})
        state.append_log({"event": "finish", "worker": "w0"})

        entries = state.tail_log()
        assert len(entries) == 2
        assert entries[0]["event"] == "start"
        assert entries[1]["event"] == "finish"
        # Timestamps should be auto-filled
        assert "timestamp" in entries[0]
        assert "timestamp" in entries[1]

    def test_tail_limit(self, tmp_path):
        """tail_log(n) only returns the last n entries."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        for i in range(10):
            state.append_log({"seq": i})

        entries = state.tail_log(n=3)
        assert len(entries) == 3
        assert entries[0]["seq"] == 7
        assert entries[1]["seq"] == 8
        assert entries[2]["seq"] == 9

    def test_append_preserves_explicit_timestamp(self, tmp_path):
        """An explicit timestamp is not overwritten."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)
        state.append_log({"event": "custom", "timestamp": "2026-01-01T00:00:00+00:00"})
        entries = state.tail_log()
        assert entries[0]["timestamp"] == "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# TestSummary
# ---------------------------------------------------------------------------


class TestSummary:
    """Tests for the summary() aggregation."""

    def test_summary_with_empty_state(self, tmp_path):
        """Summary works even when no state files exist."""
        state = ResearchState(tmp_path)
        s = state.summary()
        assert s["phase"] == "idle"
        assert s["paused"] is False
        assert s["total_experiments"] == 0
        assert s["results_by_status"] == {}
        assert s["total_hypotheses"] == 0
        assert s["frontier_size"] == 0
        assert s["workers"] == {}
        assert "config" in s

    def test_summary_with_populated_state(self, tmp_path):
        """Summary reflects actual state."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        state = ResearchState(tmp_path)

        # Set up some state
        state.update_phase("execute")
        state.update_worker("w0", status="running")
        state.append_result({"worker": "w0", "status": "keep", "metric": "acc", "value": "0.9"})
        state.append_result({"worker": "w1", "status": "discard", "metric": "acc", "value": "0.5"})
        state.append_result({"worker": "w0", "status": "keep", "metric": "acc", "value": "0.92"})

        graph = _default_graph()
        graph["hypotheses"].append({"id": "h1"})
        graph["hypotheses"].append({"id": "h2"})
        graph["frontier"].append({"id": "f1", "status": "approved"})
        state.save_graph(graph)

        s = state.summary()
        assert s["phase"] == "execute"
        assert s["total_experiments"] == 3
        assert s["results_by_status"] == {"keep": 2, "discard": 1}
        assert s["total_hypotheses"] == 2
        assert s["frontier_size"] == 1
        assert "w0" in s["workers"]


# ---------------------------------------------------------------------------
# TestDeepMerge (unit helper)
# ---------------------------------------------------------------------------


class TestDeepMerge:
    """Unit tests for the _deep_merge helper."""

    def test_empty_override(self):
        base = {"a": 1, "b": {"c": 2}}
        assert _deep_merge(base, {}) == base

    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_nested_override(self):
        base = {"x": {"y": 1, "z": 2}}
        result = _deep_merge(base, {"x": {"z": 99}})
        assert result == {"x": {"y": 1, "z": 99}}

    def test_new_keys_added(self):
        base = {"a": 1}
        result = _deep_merge(base, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_original_not_mutated(self):
        base = {"a": {"b": 1}}
        _deep_merge(base, {"a": {"b": 99}})
        assert base["a"]["b"] == 1
