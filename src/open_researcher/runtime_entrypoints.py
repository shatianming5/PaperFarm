"""Shared helpers for run/headless orchestration entrypoints."""

from __future__ import annotations

from pathlib import Path

from open_researcher.bootstrap import ensure_bootstrap_state
from open_researcher.config import load_config, require_supported_protocol
from open_researcher.graph_protocol import initialize_graph_runtime_state, resolve_role_agent_name
from open_researcher.parallel_runtime import run_parallel_experiment_batch
from open_researcher.workflow_options import apply_worker_override


def load_runtime_config(
    research: Path,
    *,
    workers: int | None,
    max_experiments: int = 0,
    token_budget: int = 0,
):
    """Load and normalize runtime config used by orchestration entrypoints."""
    cfg = apply_worker_override(load_config(research, strict=True), workers)
    require_supported_protocol(cfg)
    if max_experiments > 0:
        cfg.max_experiments = max_experiments
    if token_budget > 0:
        cfg.token_budget = token_budget
    return cfg


def resolve_scout_agent(
    cfg,
    *,
    primary_agent_name: str | None,
    resolve_agent_fn,
):
    """Resolve scout role agent with config-aware fallback semantics."""
    return resolve_agent_fn(
        resolve_role_agent_name(cfg, "scout_agent", primary_agent_name),
        cfg.agent_config,
    )


def resolve_research_agents(
    cfg,
    *,
    primary_agent_name: str | None,
    resolve_agent_fn,
):
    """Resolve manager/critic/experiment role agents."""
    manager_agent = resolve_agent_fn(
        resolve_role_agent_name(cfg, "manager_agent", primary_agent_name),
        cfg.agent_config,
    )
    critic_agent = resolve_agent_fn(
        resolve_role_agent_name(cfg, "critic_agent", primary_agent_name),
        cfg.agent_config,
    )
    exp_agent = resolve_agent_fn(
        resolve_role_agent_name(cfg, "experiment_agent", primary_agent_name),
        cfg.agent_config,
    )
    return manager_agent, critic_agent, exp_agent


def build_parallel_runner(
    *,
    repo_path: Path,
    research_dir: Path,
    cfg,
    exp_agent,
    on_output,
):
    """Build optional parallel experiment runner when workers > 1."""
    if cfg.max_workers == 1:
        return None
    return lambda **kwargs: run_parallel_experiment_batch(
        repo_path,
        research_dir,
        cfg,
        exp_agent,
        on_output,
        **kwargs,
    )


def sync_runtime_state(research: Path, cfg) -> None:
    """Ensure graph and bootstrap runtime artifacts are initialized."""
    initialize_graph_runtime_state(research, cfg)
    ensure_bootstrap_state(research / "bootstrap_state.json")
