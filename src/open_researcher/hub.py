"""PaperFarm Hub — manifest fetching and bootstrap config integration."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HUB_REGISTRY_URL = "https://raw.githubusercontent.com/XuanmiaoG/PaperFarm-Hub/main"


def _fetch_json(url: str, timeout: int = 10) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Invalid encoding in response from {url}: {exc}") from exc
            if not text.strip():
                raise ValueError(f"Empty response from {url}")
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None) or str(exc)
        raise ValueError(f"Network error fetching {url}: {reason}") from exc
    except socket.timeout as exc:
        raise ValueError(f"Timeout fetching {url} (timeout={timeout}s)") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at {url}: {exc}") from exc


def fetch_index(registry_url: str = HUB_REGISTRY_URL) -> dict[str, str]:
    """Return mapping of arxiv_id -> folder name from the Hub index (supports v1 and v2)."""
    index = _fetch_json(f"{registry_url}/index.json")
    entries = index.get("entries", {})
    # v2: entries is a list of dicts with arxiv_id + folder fields
    if isinstance(entries, list):
        return {
            str(e["arxiv_id"]): str(e["folder"])
            for e in entries
            if isinstance(e, dict)
            and isinstance(e.get("arxiv_id"), str)
            and isinstance(e.get("folder"), str)
            and e["arxiv_id"]
            and e["folder"]
        }
    # v1: entries is a flat {arxiv_id: folder} dict
    if isinstance(entries, dict):
        return entries
    raise ValueError("Hub index.json has unexpected format")


def fetch_index_full(registry_url: str = HUB_REGISTRY_URL) -> list[dict[str, Any]]:
    """Return the full index entry list (v2 only) for catalog/listing use cases."""
    index = _fetch_json(f"{registry_url}/index.json")
    entries = index.get("entries", [])
    if isinstance(entries, list):
        return entries
    # v1 fallback: synthesize minimal entry objects
    if isinstance(entries, dict):
        return [{"arxiv_id": k, "folder": v} for k, v in entries.items()]
    return []


def fetch_manifest(arxiv_id: str, registry_url: str = HUB_REGISTRY_URL) -> dict[str, Any]:
    """Fetch paperfarm.json for the given arxiv_id from the Hub registry."""
    index = fetch_index(registry_url)
    folder = index.get(arxiv_id)
    if not folder:
        raise ValueError(
            f"arxiv_id {arxiv_id!r} not found in Hub index. "
            f"Available: {', '.join(sorted(index.keys()))}"
        )
    safe_folder = urllib.parse.quote(folder, safe="")
    url = f"{registry_url}/hub/{safe_folder}/paperfarm.json"
    manifest = _fetch_json(url)
    manifest["_folder"] = folder
    return manifest


def manifest_to_bootstrap_overrides(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a paperfarm.json manifest into bootstrap config.yaml overrides.
    Only sets fields that are non-empty in the manifest.
    """
    overrides: dict[str, Any] = {}

    env = manifest.get("env") if isinstance(manifest.get("env"), dict) else {}
    if env.get("install_command"):
        overrides["install_command"] = env["install_command"]
    if env.get("test_command"):
        overrides["smoke_command"] = env["test_command"]
    if env.get("python"):
        overrides["python"] = env["python"]

    resources = manifest.get("resources") if isinstance(manifest.get("resources"), dict) else {}
    if resources.get("gpu") == "required":
        overrides["requires_gpu"] = True

    return overrides


def manifest_summary(manifest: dict[str, Any]) -> str:
    """Return a short human-readable summary of a manifest."""
    def _d(key: str) -> dict:
        val = manifest.get(key)
        return val if isinstance(val, dict) else {}

    paper = _d("paper")
    env = _d("env")
    resources = _d("resources")
    status = _d("status")
    agent = _d("agent")

    lines = [
        f"  Title   : {paper.get('title', '?')}",
        f"  ArXiv   : {paper.get('arxiv_id', '?')}",
        f"  Repo    : {manifest.get('source', {}).get('git_repo', '?')}",
        f"  Manager : {env.get('manager', '?')}  Python {env.get('python', '?')}",
        f"  Install : {env.get('install_command', '?')}",
        f"  Test    : {env.get('test_command', '?')}",
        f"  GPU     : {resources.get('gpu', '?')}",
    ]

    if resources.get("min_vram_gb"):
        lines.append(f"  VRAM    : {resources['min_vram_gb']} GB min")

    if agent:
        providers = agent.get("providers", [])
        if providers:
            names = [p["name"] for p in providers if p.get("name")]
            lines.append(f"  LLM     : {', '.join(names)}")

    verified = status.get("verified", False)
    count = status.get("verified_count", 0)
    lines.append(f"  Verified: {'yes' if verified else 'no'} ({count} report(s))")

    issues = status.get("known_issues", [])
    if issues:
        lines.append(f"  Issues  : {issues[0]}")
        for issue in issues[1:]:
            lines.append(f"            {issue}")

    return "\n".join(lines)


def apply_manifest_to_config_yaml(
    manifest: dict[str, Any],
    research_dir: Path,
) -> dict[str, Any]:
    """
    Merge manifest bootstrap overrides into .research/config.yaml.
    Returns the dict of fields that were written.
    """
    import yaml

    config_path = research_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"{config_path} not found — run `open-researcher init` first")

    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse config.yaml: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("config.yaml must be a YAML mapping")

    overrides = manifest_to_bootstrap_overrides(manifest)
    if not overrides:
        return {}

    bootstrap = raw.setdefault("bootstrap", {})
    for key, value in overrides.items():
        bootstrap[key] = value

    # Record the Hub manifest source for audit trail
    bootstrap["hub_arxiv_id"] = manifest.get("paper", {}).get("arxiv_id", "")
    bootstrap["hub_manifest_source"] = (
        f"{HUB_REGISTRY_URL}/hub/"
        f"{manifest.get('_folder', '')}/paperfarm.json"
    )

    import os
    import tempfile

    content = yaml.dump(raw, default_flow_style=False, allow_unicode=True)
    fd, tmp = tempfile.mkstemp(dir=str(config_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(config_path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return overrides
