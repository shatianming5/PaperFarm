"""Bootstrap resolution and auto-prepare helpers — compatibility re-export.

This module has been migrated to ``open_researcher.plugins.bootstrap.legacy_bootstrap``.
This file re-exports all public names for backward compatibility.
"""

from open_researcher.plugins.bootstrap.legacy_bootstrap import (  # noqa: F401
    BOOTSTRAP_STATE_VERSION,
    PREPARE_LOG_NAME,
    SMOKE_PREFLIGHT_ATTEMPTS,
    command_env_for_python,
    default_bootstrap_state,
    detect_repo_profile,
    ensure_bootstrap_state,
    format_bootstrap_dry_run,
    is_prepare_ready,
    read_bootstrap_state,
    resolve_bootstrap_plan,
    resolve_python_environment,
    run_bootstrap_prepare,
    write_bootstrap_state,
)
