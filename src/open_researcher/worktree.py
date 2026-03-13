"""Git worktree helpers — compatibility re-export.

This module has been migrated to ``open_researcher.plugins.execution.legacy_worktree``.
This file re-exports all public names for backward compatibility.
"""

from open_researcher.plugins.execution.legacy_worktree import (  # noqa: F401
    WorktreeError,
    create_worktree,
    remove_worktree,
    worktrees_root,
)
