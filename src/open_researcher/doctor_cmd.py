"""Health check command for the research environment."""

import json
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from open_researcher.config import RESEARCH_PROTOCOL, load_config


REQUIRED_ROLE_PROGRAMS = [
    "scout_program.md",
    "manager_program.md",
    "critic_program.md",
    "experiment_program.md",
]


def _load_json_object(path: Path) -> tuple[dict | None, str | None]:
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"Parse error: {exc}"
    if not isinstance(payload, dict):
        return None, "top-level JSON must be an object"
    return payload, None


def _require_list_field(payload: dict, key: str) -> str | None:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return f"{key} must be a list"
    return None


def run_doctor(repo_path: Path) -> list[dict]:
    """Run health checks. Returns list of {check, status, detail}."""
    results: list[dict] = []
    research = repo_path / ".research"

    # 1. Git repository
    git_dir = repo_path / ".git"
    if git_dir.exists():
        results.append({"check": "Git repository", "status": "OK", "detail": str(git_dir)})
    else:
        results.append({"check": "Git repository", "status": "FAIL", "detail": ".git not found"})

    # 2. .research/ directory
    if research.is_dir():
        results.append({"check": ".research/ directory", "status": "OK", "detail": str(research)})
    else:
        results.append({"check": ".research/ directory", "status": "FAIL", "detail": ".research/ not found"})

    # 3. config.yaml parseable
    config_path = research / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            yaml.safe_load(config_path.read_text())
            results.append({"check": "config.yaml", "status": "OK", "detail": "Parseable"})
        except Exception as exc:
            results.append({"check": "config.yaml", "status": "FAIL", "detail": f"Parse error: {exc}"})
    else:
        results.append({"check": "config.yaml", "status": "WARN", "detail": "File not found"})

    try:
        protocol = load_config(research, strict=True).protocol
        if protocol == RESEARCH_PROTOCOL:
            results.append({"check": "research.protocol", "status": "OK", "detail": protocol})
        else:
            results.append(
                {
                    "check": "research.protocol",
                    "status": "FAIL",
                    "detail": f"Unsupported protocol {protocol!r}",
                }
            )
    except ValueError as exc:
        results.append({"check": "research.protocol", "status": "FAIL", "detail": str(exc)})

    # 4. results.tsv exists
    results_path = research / "results.tsv"
    if results_path.exists():
        results.append({"check": "results.tsv", "status": "OK", "detail": "Exists"})
    else:
        results.append({"check": "results.tsv", "status": "WARN", "detail": "File not found"})

    # 5. research_graph.json parseable
    graph_path = research / "research_graph.json"
    if graph_path.exists():
        graph, error = _load_json_object(graph_path)
        if error is not None:
            results.append({"check": "research_graph.json", "status": "FAIL", "detail": error})
        else:
            field_error = (
                _require_list_field(graph, "frontier")
                or _require_list_field(graph, "hypotheses")
                or _require_list_field(graph, "experiment_specs")
                or _require_list_field(graph, "evidence")
                or _require_list_field(graph, "claim_updates")
            )
            if field_error is not None:
                results.append({"check": "research_graph.json", "status": "FAIL", "detail": field_error})
            else:
                frontier_count = len(graph.get("frontier", []))
                results.append({"check": "research_graph.json", "status": "OK", "detail": f"{frontier_count} frontier rows"})
    else:
        results.append({"check": "research_graph.json", "status": "WARN", "detail": "File not found"})

    # 6. research_memory.json parseable
    memory_path = research / "research_memory.json"
    if memory_path.exists():
        memory, error = _load_json_object(memory_path)
        if error is not None:
            results.append({"check": "research_memory.json", "status": "FAIL", "detail": error})
        else:
            field_error = _require_list_field(memory, "ideation_memory") or _require_list_field(memory, "experiment_memory")
            if field_error is not None:
                results.append({"check": "research_memory.json", "status": "FAIL", "detail": field_error})
            else:
                ideation = len(memory.get("ideation_memory", []))
                experiment = len(memory.get("experiment_memory", []))
                detail = f"ideation={ideation}, experiment={experiment}"
                results.append({"check": "research_memory.json", "status": "OK", "detail": detail})
    else:
        results.append({"check": "research_memory.json", "status": "WARN", "detail": "File not found"})

    # 7. idea_pool.json parseable
    pool_path = research / "idea_pool.json"
    if pool_path.exists():
        data, error = _load_json_object(pool_path)
        if error is not None:
            results.append({"check": "idea_pool.json", "status": "FAIL", "detail": error})
        else:
            field_error = _require_list_field(data, "ideas")
            if field_error is not None:
                results.append({"check": "idea_pool.json", "status": "FAIL", "detail": field_error})
            else:
                count = len(data.get("ideas", []))
                results.append({"check": "idea_pool.json", "status": "OK", "detail": f"{count} projected backlog rows"})
    else:
        results.append({"check": "idea_pool.json", "status": "WARN", "detail": "File not found"})

    # 8. activity.json parseable
    activity_path = research / "activity.json"
    if activity_path.exists():
        _activity, error = _load_json_object(activity_path)
        if error is not None:
            results.append({"check": "activity.json", "status": "FAIL", "detail": error})
        else:
            results.append({"check": "activity.json", "status": "OK", "detail": "Parseable"})
    else:
        results.append({"check": "activity.json", "status": "WARN", "detail": "File not found"})

    # 9. required role programs present
    missing_programs = [name for name in REQUIRED_ROLE_PROGRAMS if not (research / name).exists()]
    if not missing_programs:
        results.append({"check": "role programs", "status": "OK", "detail": ", ".join(REQUIRED_ROLE_PROGRAMS)})
    else:
        results.append({"check": "role programs", "status": "FAIL", "detail": f"Missing: {', '.join(missing_programs)}"})

    # 10. experiment_progress.json parseable
    progress_path = research / "experiment_progress.json"
    if progress_path.exists():
        progress, error = _load_json_object(progress_path)
        if error is not None:
            results.append({"check": "experiment_progress.json", "status": "FAIL", "detail": error})
        else:
            phase = progress.get("phase", "<missing>")
            results.append({"check": "experiment_progress.json", "status": "OK", "detail": f"phase={phase}"})
    else:
        results.append({"check": "experiment_progress.json", "status": "WARN", "detail": "File not found"})

    # 11. events.jsonl parseable with seq
    events_path = research / "events.jsonl"
    if events_path.exists():
        try:
            total = 0
            last_seq = 0
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("event record must be a JSON object")
                total += 1
                seq = int(record.get("seq"))
                if seq <= 0:
                    raise ValueError("seq must be a positive integer")
                if seq < last_seq:
                    raise ValueError("seq is not monotonic")
                last_seq = seq
            results.append({"check": "events.jsonl", "status": "OK", "detail": f"{total} event(s), last_seq={last_seq}"})
        except (TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
            results.append({"check": "events.jsonl", "status": "FAIL", "detail": f"Parse error: {exc}"})
    else:
        results.append({"check": "events.jsonl", "status": "WARN", "detail": "File not found"})

    # 12. Agent binaries on PATH
    agents = ["claude", "codex", "aider", "opencode"]
    found = [a for a in agents if shutil.which(a)]
    missing = [a for a in agents if not shutil.which(a)]
    if found:
        detail = f"Found: {', '.join(found)}"
        if missing:
            detail += f"; Missing: {', '.join(missing)}"
        status = "OK" if not missing else "WARN"
        results.append({"check": "Agent binaries", "status": status, "detail": detail})
    else:
        results.append({"check": "Agent binaries", "status": "WARN", "detail": "No agents found on PATH"})

    # 13. Python >= 3.10
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        results.append({"check": "Python >= 3.10", "status": "OK", "detail": f"{major}.{minor}"})
    else:
        results.append(
            {"check": "Python >= 3.10", "status": "FAIL", "detail": f"{major}.{minor} (need >= 3.10)"}
        )

    return results


def print_doctor(repo_path: Path) -> None:
    """Print doctor results as a Rich table."""
    checks = run_doctor(repo_path)
    console = Console()
    table = Table(title="Research Environment Health Check")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    status_style = {
        "OK": "[green][OK][/green]",
        "WARN": "[yellow][WARN][/yellow]",
        "FAIL": "[red][FAIL][/red]",
    }

    for check in checks:
        table.add_row(
            check["check"],
            status_style.get(check["status"], check["status"]),
            check["detail"],
        )

    console.print(table)
