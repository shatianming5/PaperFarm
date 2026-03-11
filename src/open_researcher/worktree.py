"""Git worktree helpers for parallel experiment isolation."""

import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_WORKTREE_ROOT_PREFIX = ".open-researcher-worktrees-"


class WorktreeError(RuntimeError):
    """Raised when isolated worktree setup or cleanup fails."""


def worktrees_root(repo_path: Path) -> Path:
    """Return the external root used for isolated experiment worktrees."""
    resolved_repo = repo_path.resolve()
    digest = hashlib.sha1(str(resolved_repo).encode("utf-8")).hexdigest()[:10]
    dirname = f"{_WORKTREE_ROOT_PREFIX}{resolved_repo.name}-{digest}"
    return resolved_repo.parent / dirname


def create_worktree(repo_path: Path, worktree_name: str) -> Path:
    """Create an isolated git worktree for a parallel worker.

    Creates a new branch and worktree under an external worktree root.
    Replaces the worktree's `.research/` directory with a directory symlink
    back to the canonical repo state so atomic writes and lock files stay
    shared across workers.

    Returns the worktree path.
    """
    research_dir = repo_path / ".research"
    worktrees_dir = worktrees_root(repo_path)
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    wt_path = worktrees_dir / worktree_name
    branch_name = f"or-worker-{worktree_name}"

    _run_git(repo_path, "worktree", "prune")

    # Remove stale worktree if it exists
    if wt_path.exists():
        remove_worktree(repo_path, wt_path)
    elif _branch_exists(repo_path, branch_name):
        _run_git(repo_path, "branch", "-D", branch_name)

    _run_git(repo_path, "worktree", "add", "-b", branch_name, str(wt_path), "HEAD")

    try:
        # Replace the checked-out .research tree with a shared directory symlink so
        # all state files and their companion *.lock files resolve canonically.
        _replace_research_dir(wt_path, research_dir)
    except Exception as exc:
        try:
            remove_worktree(repo_path, wt_path)
        except Exception as cleanup_exc:  # pragma: no cover - best-effort context enrichment
            raise WorktreeError(
                f"Failed to finish worktree setup ({exc}) and cleanup failed ({cleanup_exc})"
            ) from cleanup_exc
        raise WorktreeError(f"Failed to finish worktree setup: {exc}") from exc

    logger.debug("Created worktree %s (branch %s)", wt_path, branch_name)
    return wt_path


def _replace_research_dir(worktree_path: Path, research_dir: Path) -> None:
    """Replace the worktree's .research directory with a shared symlink."""
    wt_research = worktree_path / ".research"
    if wt_research.is_symlink() or wt_research.is_file():
        wt_research.unlink()
    elif wt_research.is_dir():
        shutil.rmtree(wt_research)
    os.symlink(str(research_dir.resolve()), str(wt_research))


def remove_worktree(repo_path: Path, worktree_path: Path) -> None:
    """Remove a git worktree and its branch."""
    wt_name = worktree_path.name
    branch_name = f"or-worker-{wt_name}"
    _run_git(repo_path, "worktree", "prune")

    # Remove the shared .research symlink first (git worktree remove dislikes it)
    wt_research = worktree_path / ".research"
    if wt_research.is_symlink() or wt_research.is_file():
        wt_research.unlink()
    elif wt_research.is_dir():
        shutil.rmtree(wt_research, ignore_errors=True)

    if worktree_path.exists():
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)
        if worktree_path.exists():
            detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
            raise WorktreeError(f"Failed to remove worktree {worktree_path}: {detail}")

    _run_git(repo_path, "worktree", "prune")
    if _branch_exists(repo_path, branch_name):
        _run_git(repo_path, "branch", "-D", branch_name)

    root = worktree_path.parent
    if root.exists() and root.name.startswith(_WORKTREE_ROOT_PREFIX):
        try:
            next(root.iterdir())
        except StopIteration:
            root.rmdir()

    logger.debug("Removed worktree %s", worktree_path)


def _branch_exists(repo_path: Path, branch_name: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise WorktreeError(f"git {' '.join(args)} failed: {detail}")
    return result
