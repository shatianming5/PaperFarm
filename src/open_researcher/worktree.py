"""Git worktree helpers for parallel experiment isolation."""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Files/dirs inside .research/ that should NOT be symlinked into worktrees
# (worktrees itself would create circular symlinks; run.log is shared)
_EXCLUDE = {"worktrees", "run.log"}


def create_worktree(repo_path: Path, worktree_name: str) -> Path:
    """Create an isolated git worktree for a parallel worker.

    Creates a new branch and worktree under .research/worktrees/<name>.
    Symlinks the shared .research/ contents (except worktrees/) so the agent
    can access idea_pool, results, config, etc.

    Returns the worktree path.
    """
    research_dir = repo_path / ".research"
    worktrees_dir = research_dir / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    wt_path = worktrees_dir / worktree_name
    branch_name = f"or-worker-{worktree_name}"

    # Remove stale worktree if it exists
    if wt_path.exists():
        remove_worktree(repo_path, wt_path)

    # Create worktree with a new branch from HEAD
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(wt_path), "HEAD"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=True,
    )

    # Symlink shared .research/ contents into the worktree
    _link_research(wt_path, research_dir)

    logger.debug("Created worktree %s (branch %s)", wt_path, branch_name)
    return wt_path


def _link_research(worktree_path: Path, research_dir: Path) -> None:
    """Create .research/ in the worktree with symlinks to shared state files.

    Individual files/dirs from the main .research/ are symlinked, except for
    the worktrees/ directory itself (avoids circular symlinks) and run.log.
    """
    wt_research = worktree_path / ".research"
    wt_research.mkdir(exist_ok=True)

    for item in research_dir.iterdir():
        if item.name in _EXCLUDE:
            continue
        target = wt_research / item.name
        if not target.exists():
            os.symlink(str(item.resolve()), str(target))


def remove_worktree(repo_path: Path, worktree_path: Path) -> None:
    """Remove a git worktree and its branch."""
    wt_name = worktree_path.name
    branch_name = f"or-worker-{wt_name}"

    # Remove the .research symlinks first (git worktree remove dislikes them)
    wt_research = worktree_path / ".research"
    if wt_research.is_dir():
        for item in wt_research.iterdir():
            if item.is_symlink():
                item.unlink()
        try:
            wt_research.rmdir()
        except OSError:
            pass

    # Remove worktree
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )

    # Delete the temporary branch
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )

    logger.debug("Removed worktree %s", worktree_path)
