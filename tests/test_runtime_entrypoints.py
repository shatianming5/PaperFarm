"""Tests for shared runtime entrypoint helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from open_researcher.config import ResearchConfig
from open_researcher.runtime_entrypoints import (
    build_parallel_runner,
    load_runtime_config,
    resolve_research_agents,
    resolve_scout_agent,
    sync_runtime_state,
)


def test_load_runtime_config_applies_cli_overrides(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(yaml.dump({"research": {"protocol": "research-v1"}}), encoding="utf-8")

    cfg = load_runtime_config(
        research,
        workers=3,
        max_experiments=12,
        token_budget=3456,
    )

    assert cfg.max_workers == 3
    assert cfg.max_experiments == 12
    assert cfg.token_budget == 3456


def test_load_runtime_config_rejects_unsupported_protocol(tmp_path):
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(yaml.dump({"research": {"protocol": "wrong"}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_runtime_config(research, workers=None)


def test_resolve_research_agents_respects_role_overrides_and_fallback():
    cfg = ResearchConfig(
        role_agents={
            "manager_agent": "gemini",
            "critic_agent": "claude-code",
        },
        agent_config={
            "gemini": {"model": "gemini-2.5-pro"},
            "claude-code": {"model": "sonnet"},
        },
    )
    calls: list[tuple[str | None, dict | None]] = []

    def fake_resolve_agent(name: str | None, agent_config: dict | None):
        calls.append((name, agent_config))
        return SimpleNamespace(name=name)

    manager, critic, exp = resolve_research_agents(
        cfg,
        primary_agent_name="codex",
        resolve_agent_fn=fake_resolve_agent,
    )

    assert manager.name == "gemini"
    assert critic.name == "claude-code"
    assert exp.name == "codex"
    assert calls == [
        ("gemini", cfg.agent_config),
        ("claude-code", cfg.agent_config),
        ("codex", cfg.agent_config),
    ]


def test_resolve_scout_agent_falls_back_to_primary_agent():
    cfg = ResearchConfig(agent_config={"codex": {"model": "o4-mini"}})
    calls: list[tuple[str | None, dict | None]] = []

    def fake_resolve_agent(name: str | None, agent_config: dict | None):
        calls.append((name, agent_config))
        return SimpleNamespace(name=name)

    scout = resolve_scout_agent(
        cfg,
        primary_agent_name="codex",
        resolve_agent_fn=fake_resolve_agent,
    )

    assert scout.name == "codex"
    assert calls == [("codex", cfg.agent_config)]


def test_build_parallel_runner_none_for_single_worker(tmp_path):
    repo = tmp_path / "repo"
    research = repo / ".research"
    research.mkdir(parents=True)
    cfg = ResearchConfig(max_workers=1)

    runner = build_parallel_runner(
        repo_path=repo,
        research_dir=research,
        cfg=cfg,
        exp_agent=SimpleNamespace(name="codex"),
        on_output=lambda _line: None,
    )

    assert runner is None


def test_build_parallel_runner_calls_parallel_runtime(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    research = repo / ".research"
    research.mkdir(parents=True)
    cfg = ResearchConfig(max_workers=2)
    exp_agent = SimpleNamespace(name="codex")

    def on_output(_line: str) -> None:
        return None

    captured: dict[str, object] = {}

    def fake_parallel_runner(repo_path, research_dir, cfg_obj, exp_agent_obj, on_output_cb, **kwargs):
        captured["repo_path"] = repo_path
        captured["research_dir"] = research_dir
        captured["cfg"] = cfg_obj
        captured["exp_agent"] = exp_agent_obj
        captured["on_output"] = on_output_cb
        captured["kwargs"] = kwargs
        return {"exit_code": 0}

    monkeypatch.setattr(
        "open_researcher.runtime_entrypoints.run_parallel_experiment_batch",
        fake_parallel_runner,
    )

    runner = build_parallel_runner(
        repo_path=repo,
        research_dir=research,
        cfg=cfg,
        exp_agent=exp_agent,
        on_output=on_output,
    )
    assert runner is not None

    result = runner(batch_id="test")
    assert result == {"exit_code": 0}
    assert captured["repo_path"] == repo
    assert captured["research_dir"] == research
    assert captured["cfg"] is cfg
    assert captured["exp_agent"] is exp_agent
    assert captured["on_output"] is on_output
    assert captured["kwargs"] == {"batch_id": "test"}


def test_sync_runtime_state_initializes_graph_and_bootstrap(monkeypatch, tmp_path):
    research = tmp_path / ".research"
    research.mkdir()
    cfg = SimpleNamespace(mode="autonomous")
    calls: dict[str, object] = {}

    def fake_init_graph(research_dir, cfg_obj):
        calls["init_graph"] = (research_dir, cfg_obj)
        return {}

    def fake_ensure_bootstrap(path):
        calls["ensure_bootstrap"] = path

    monkeypatch.setattr("open_researcher.runtime_entrypoints.initialize_graph_runtime_state", fake_init_graph)
    monkeypatch.setattr("open_researcher.runtime_entrypoints.ensure_bootstrap_state", fake_ensure_bootstrap)

    sync_runtime_state(research, cfg)

    assert calls["init_graph"] == (research, cfg)
    assert calls["ensure_bootstrap"] == research / "bootstrap_state.json"
