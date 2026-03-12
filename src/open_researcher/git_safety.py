"""Git workspace safety helpers for experiment runtime."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from open_researcher.workspace_paths import (
    OVERLAY_MANIFEST_FILENAME,
    is_runtime_artifact_path,
    normalize_relative_path,
    overlay_manifest_entry_for_path,
)


class GitWorkspaceError(RuntimeError):
    """Raised when the experiment workspace is not safe to use."""


@dataclass(frozen=True, slots=True)
class GitWorkspaceSnapshot:
    """Minimal git snapshot required to restore a workspace."""

    head: str


@dataclass(frozen=True, slots=True)
class GitStatusEntry:
    """One porcelain status entry."""

    code: str
    path: str


def capture_clean_workspace_snapshot(repo_path: Path) -> GitWorkspaceSnapshot:
    """Capture HEAD after verifying the workspace is clean enough for runtime."""
    head = _run_git(repo_path, "rev-parse", "HEAD").stdout.strip()
    ensure_clean_workspace(repo_path, context="before experiment")
    return GitWorkspaceSnapshot(head=head)


def ensure_clean_workspace(repo_path: Path, *, context: str) -> None:
    """Raise when the workspace contains non-runtime changes."""
    changes = _workspace_changes(repo_path)
    if changes:
        raise GitWorkspaceError(f"Git workspace {context} is dirty: {_format_changes(changes)}")


def rollback_workspace(repo_path: Path, snapshot: GitWorkspaceSnapshot) -> None:
    """Restore the workspace back to the recorded snapshot, preserving .research."""
    _run_git(repo_path, "reset", "--hard", snapshot.head)
    for entry in _workspace_changes(repo_path):
        _remove_path(repo_path, entry.path)
    ensure_clean_workspace(repo_path, context="after rollback")


def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise GitWorkspaceError(f"git {' '.join(args)} failed: {detail}")
    return result


def _workspace_changes(repo_path: Path) -> list[GitStatusEntry]:
    result = _run_git(repo_path, "status", "--porcelain=v1", "--untracked-files=all")
    overlay_manifest = _load_overlay_manifest(repo_path)
    changes: list[GitStatusEntry] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path and ("R" in code or "C" in code):
            _old_path, path = path.split(" -> ", 1)
        normalized = normalize_relative_path(path)
        if normalized and _is_synced_overlay_path(repo_path, normalized, code=code, manifest=overlay_manifest):
            continue
        if normalized and not is_runtime_artifact_path(normalized):
            changes.append(GitStatusEntry(code=code, path=normalized))
    return changes


def _load_overlay_manifest(repo_path: Path) -> dict[str, dict]:
    manifest_path = _overlay_manifest_path(repo_path)
    if manifest_path is None or not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    paths = payload.get("paths", {})
    return paths if isinstance(paths, dict) else {}


def _overlay_manifest_path(repo_path: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo_path / git_dir).resolve()
    return git_dir / OVERLAY_MANIFEST_FILENAME


def _is_synced_overlay_path(repo_path: Path, relative_path: str, *, code: str, manifest: dict[str, dict]) -> bool:
    if code != "??":
        return False
    entry = manifest.get(relative_path)
    if not isinstance(entry, dict):
        return False
    current = overlay_manifest_entry_for_path(repo_path / relative_path)
    return current == entry


def _format_changes(changes: list[GitStatusEntry], *, limit: int = 5) -> str:
    preview = [f"{entry.code} {entry.path}" for entry in changes[:limit]]
    if len(changes) > limit:
        preview.append(f"... +{len(changes) - limit} more")
    return ", ".join(preview)


def _remove_path(repo_path: Path, relative_path: str) -> None:
    root = repo_path.resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise GitWorkspaceError(f"Refusing to remove path outside repo: {relative_path}") from exc
    if not target.exists() and not target.is_symlink():
        return
    if target.is_symlink() or target.is_file():
        target.unlink()
        return
    shutil.rmtree(target)
