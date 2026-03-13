"""Helpers for keeping the evaluation contract executable in research-v1."""

from __future__ import annotations

from pathlib import Path

import yaml

from open_researcher.config import ResearchConfig
from open_researcher.plugins.storage.file_ops import atomic_write_text

_PLACEHOLDER_MARKERS = (
    "<!-- e.g.",
    "# Exact command to run evaluation",
    "# How to extract the primary metric value from output",
    "This file is filled by the AI agent during Phase 2.",
)


def _load_graph_payload(graph_path: Path, graph_payload: dict | None) -> dict:
    if isinstance(graph_payload, dict):
        return graph_payload
    if not graph_path.exists():
        return {}
    try:
        loaded = yaml.safe_load(graph_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _load_config_payload(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_primary_metric(text: str) -> tuple[str, str]:
    metric_name = ""
    direction = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- **Name:**"):
            metric_name = line.split(":", 1)[1].strip()
        elif line.startswith("- **Direction:**"):
            direction = line.split(":", 1)[1].strip()
    if metric_name.startswith("<!--"):
        metric_name = ""
    if direction.startswith("<!--"):
        direction = ""
    return metric_name, direction


def evaluation_doc_needs_backfill(path: Path) -> bool:
    """Return True when evaluation.md is missing or still effectively a template."""
    if not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    stripped = text.strip()
    if not stripped:
        return True
    metric_name, direction = _extract_primary_metric(text)
    if any(marker in text for marker in _PLACEHOLDER_MARKERS):
        return True
    return not (metric_name and direction)


def infer_primary_metric(cfg: ResearchConfig, graph_payload: dict | None = None) -> tuple[str, str]:
    """Infer the primary metric contract from config first, then repo_profile."""
    metric_name = str(cfg.primary_metric or "").strip()
    direction = str(cfg.direction or "").strip()
    graph = graph_payload if isinstance(graph_payload, dict) else {}
    repo_profile = graph.get("repo_profile", {}) if isinstance(graph.get("repo_profile"), dict) else {}
    if not metric_name:
        metric_name = str(repo_profile.get("primary_metric", "")).strip()
    if not direction:
        direction = str(repo_profile.get("direction", "")).strip()
    if metric_name and not direction:
        direction = "higher_is_better"
    return metric_name, direction


def _render_minimal_evaluation_doc(metric_name: str, direction: str, smoke_command: str) -> str:
    command_lines = [
        "# Run the selected frontier row's experiment_spec command for the active research-v1 item.",
    ]
    if smoke_command:
        command_lines.extend(
            [
                "# Repo-level anchor / readiness fallback smoke command:",
                smoke_command,
            ]
        )
    extract_lines = [
        "python - <<'PY'",
        "import csv",
        "from pathlib import Path",
        "rows = list(csv.DictReader(Path('.research/results.tsv').open(encoding='utf-8'), delimiter='\\t'))",
        "if not rows:",
        "    raise SystemExit('no results recorded in .research/results.tsv')",
        "row = rows[-1]",
        "print(f\"{row['primary_metric']}\\t{row['metric_value']}\")",
        "PY",
    ]
    why = (
        "Use the repo's declared primary metric and the framework-recorded result row so "
        "critic/experiment roles share the same measurement contract."
    )
    return (
        "# Evaluation Design\n\n"
        "## Primary Metric\n\n"
        f"- **Name:** {metric_name}\n"
        f"- **Direction:** {direction}\n"
        f"- **Why this metric:** {why}\n\n"
        "## How to Measure\n\n"
        "### Command\n\n"
        "```bash\n"
        f"{chr(10).join(command_lines)}\n"
        "```\n\n"
        "### Extracting the Metric\n\n"
        "```bash\n"
        f"{chr(10).join(extract_lines)}\n"
        "```\n\n"
        "## Secondary Metrics (Optional)\n\n"
        "| Metric | How to Extract | Purpose |\n"
        "|--------|---------------|---------|\n"
        "| secondary_metrics | Read the `secondary_metrics` column from the newest"
        " `.research/results.tsv` row | Resource and stability context |\n\n"
        "## Baseline Method\n\n"
        "- Use the first successful anchor/reproduction result row in"
        " `.research/results.tsv` as the baseline reference.\n"
    )


def _update_config_metrics(config_path: Path, metric_name: str, direction: str) -> bool:
    if not metric_name or not direction:
        return False
    payload = _load_config_payload(config_path)
    metrics = payload.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
        payload["metrics"] = metrics
    primary = metrics.setdefault("primary", {})
    if not isinstance(primary, dict):
        primary = {}
        metrics["primary"] = primary
    changed = False
    if not str(primary.get("name", "")).strip():
        primary["name"] = metric_name
        changed = True
    if not str(primary.get("direction", "")).strip():
        primary["direction"] = direction
        changed = True
    if changed:
        atomic_write_text(config_path, yaml.safe_dump(payload, sort_keys=False))
    return changed


def _resolve_smoke_command(research_dir: Path, cfg: ResearchConfig) -> str:
    smoke_command = str(cfg.bootstrap_smoke_command or "").strip()
    if smoke_command:
        return smoke_command
    payload = _load_config_payload(research_dir / "config.yaml")
    bootstrap = payload.get("bootstrap", {}) if isinstance(payload.get("bootstrap"), dict) else {}
    return str(bootstrap.get("smoke_command", "")).strip()


def ensure_evaluation_contract(
    research_dir: Path,
    cfg: ResearchConfig,
    *,
    graph_payload: dict | None = None,
) -> dict[str, object]:
    """Backfill a minimal executable evaluation contract when scout left placeholders."""
    graph = _load_graph_payload(research_dir / "research_graph.json", graph_payload)
    metric_name, direction = infer_primary_metric(cfg, graph)
    smoke_command = _resolve_smoke_command(research_dir, cfg)
    updated_config = _update_config_metrics(research_dir / "config.yaml", metric_name, direction)

    evaluation_path = research_dir / "evaluation.md"
    updated_evaluation = False
    if metric_name and direction and evaluation_doc_needs_backfill(evaluation_path):
        atomic_write_text(
            evaluation_path,
            _render_minimal_evaluation_doc(metric_name, direction, smoke_command),
        )
        updated_evaluation = True

    return {
        "updated": updated_config or updated_evaluation,
        "updated_config": updated_config,
        "updated_evaluation": updated_evaluation,
        "primary_metric": metric_name,
        "direction": direction,
    }
