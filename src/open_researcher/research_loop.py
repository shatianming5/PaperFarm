"""Core research loop — compatibility re-export.

This module has been migrated to ``open_researcher.plugins.orchestrator.legacy_loop``.
This file re-exports all public names for backward compatibility.
"""

from open_researcher.plugins.orchestrator.legacy_loop import (  # noqa: F401
    ResearchLoop,
    has_pending_ideas,
    read_latest_status,
    set_paused,
)
