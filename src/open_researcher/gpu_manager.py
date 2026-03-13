"""GPU manager — compatibility re-export.

This module has been migrated to ``open_researcher.plugins.execution.legacy_gpu``.
This file re-exports all public names for backward compatibility.
"""

from open_researcher.plugins.execution.legacy_gpu import (  # noqa: F401
    GPUManager,
    parse_visible_cuda_devices,
)
