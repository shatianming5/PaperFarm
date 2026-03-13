"""AgentAdapter ABC -- the interface every agent backend must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


class AgentAdapter(ABC):
    """Abstract base class for agent adapters.

    Subclasses must set ``name`` and implement the three abstract methods.
    """

    name: str = ""

    @abstractmethod
    def check_installed(self) -> bool:
        """Return True if this agent backend is available on the system."""
        ...

    @abstractmethod
    def run(
        self,
        repo_path: str | Path,
        program_file: str | Path,
        *,
        on_output: Callable[[str], None] | None = None,
        env: dict[str, str] | None = None,
    ) -> int:
        """Execute the agent and return its exit code."""
        ...

    @abstractmethod
    def terminate(self) -> None:
        """Request graceful termination of a running agent process."""
        ...
