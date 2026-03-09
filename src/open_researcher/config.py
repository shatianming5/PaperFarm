"""Typed config reader for .research/config.yaml."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ResearchConfig:
    mode: str = "autonomous"
    timeout: int = 600
    max_crashes: int = 3
    max_workers: int = 0
    worker_agent: str = ""
    primary_metric: str = ""
    direction: str = ""
    web_search: bool = True
    search_interval: int = 5
    remote_hosts: list = field(default_factory=list)


def load_config(research_dir: Path) -> ResearchConfig:
    """Load and parse config.yaml into a typed dataclass."""
    config_path = research_dir / "config.yaml"
    if not config_path.exists():
        return ResearchConfig()
    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError:
        return ResearchConfig()
    exp = raw.get("experiment", {})
    metrics = raw.get("metrics", {}).get("primary", {})
    gpu = raw.get("gpu", {})
    research = raw.get("research", {})
    return ResearchConfig(
        mode=raw.get("mode", "autonomous"),
        timeout=exp.get("timeout", 600),
        max_crashes=exp.get("max_consecutive_crashes", 3),
        max_workers=exp.get("max_parallel_workers", 0),
        worker_agent=exp.get("worker_agent", ""),
        primary_metric=metrics.get("name", ""),
        direction=metrics.get("direction", ""),
        web_search=research.get("web_search", True),
        search_interval=research.get("search_interval", 5),
        remote_hosts=gpu.get("remote_hosts", []),
    )
