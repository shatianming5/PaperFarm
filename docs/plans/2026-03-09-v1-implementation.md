# Open Researcher v1.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform open-researcher from MVP (565 lines) into a production-ready, publishable CLI framework with agent integration, real-time TUI, complete test suite, and professional project infrastructure.

**Architecture:** Add an agent integration layer (`agents/` module) with adapter pattern for Claude Code, codex-cli, aider, opencode. Add `run` command that launches agents in subprocess with real-time Rich TUI progress display. Fix all code quality issues (i18n, hardcoded paths), add project infrastructure (README, LICENSE, CI), and create demo cases.

**Tech Stack:** Python 3.10+, Typer, Rich (Live + Layout), FastAPI, Jinja2, PyYAML, pytest, ruff, GitHub Actions

---

### Task 1: Project Infrastructure Files

**Files:**
- Create: `.gitignore`
- Create: `LICENSE`
- Modify: `pyproject.toml`
- Create: `Makefile`

**Step 1: Create .gitignore**

Create `.gitignore`:

```
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
env/
.pytest_cache/
.ruff_cache/
.mypy_cache/
htmlcov/
.coverage
*.log
.DS_Store
```

**Step 2: Create LICENSE (MIT)**

Create `LICENSE`:

```
MIT License

Copyright (c) 2026 Open Researcher Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Step 3: Update pyproject.toml**

Replace the entire `pyproject.toml` with:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "open-researcher"
version = "0.1.0"
description = "Let AI agents run experiments in any repo while you sleep."
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [
    { name = "Open Researcher Contributors" },
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: Software Development :: Testing",
]
keywords = ["ai", "research", "experiments", "automation", "agent"]
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "httpx>=0.25.0",
    "ruff>=0.4.0",
]

[project.scripts]
open-researcher = "open_researcher.cli:app"

[project.urls]
Homepage = "https://github.com/open-researcher/open-researcher"
Repository = "https://github.com/open-researcher/open-researcher"
Issues = "https://github.com/open-researcher/open-researcher/issues"

[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 4: Create Makefile**

Create `Makefile`:

```makefile
.PHONY: install dev test lint clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
```

**Step 5: Commit**

```bash
git add .gitignore LICENSE pyproject.toml Makefile
git commit -m "chore: add project infrastructure (LICENSE, .gitignore, Makefile, pyproject.toml updates)"
```

---

### Task 2: Internationalize status_cmd.py

**Files:**
- Modify: `src/open_researcher/status_cmd.py`
- Modify: `tests/test_status.py`

**Context:** `status_cmd.py` has 14 Chinese UI strings. Dashboard's `index.html` already uses English. All other modules use English. We need consistency.

**Step 1: Write failing test for English output**

Add to `tests/test_status.py`:

```python
def test_print_status_english_output(capsys):
    """Verify status output uses English, not Chinese."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        research = repo / ".research"
        research.mkdir()
        # minimal config
        (research / "config.yaml").write_text("mode: autonomous\nmetrics:\n  primary:\n    name: accuracy\n    direction: higher_is_better\n")
        (research / "results.tsv").write_text("timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n")
        (research / "project-understanding.md").write_text("<!-- placeholder -->\n")
        (research / "evaluation.md").write_text("<!-- placeholder -->\n")
        print_status(repo)
        captured = capsys.readouterr()
        # Must contain English phase names
        assert "Phase 1" in captured.out
        # Must NOT contain Chinese
        assert "阶段" not in captured.out
        assert "分支" not in captured.out
        assert "模式" not in captured.out
        assert "实验统计" not in captured.out
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_status.py::test_print_status_english_output -v`
Expected: FAIL because status output contains Chinese characters.

**Step 3: Update status_cmd.py — replace all Chinese strings with English**

In `src/open_researcher/status_cmd.py`, make these changes:

Replace the `PHASE_NAMES` dict:
```python
# OLD:
PHASE_NAMES = {
    1: "理解项目 (Phase 1)",
    2: "设计评估 (Phase 2)",
    3: "建立基线 (Phase 3)",
    4: "实验循环 (Phase 4)",
}
# NEW:
PHASE_NAMES = {
    1: "Phase 1: Understand Project",
    2: "Phase 2: Design Evaluation",
    3: "Phase 3: Establish Baseline",
    4: "Phase 4: Experiment Loop",
}
```

Replace all Chinese labels in `print_status()`:
```python
# OLD labels → NEW labels mapping:
# "阶段:" → "Phase:"
# "分支:" → "Branch:"
# "模式:" → "Mode:"
# "实验统计:" → "Experiments:"
# "主要指标:" → "Primary Metric:"
# "基线:" → "Baseline:"
# "当前:" → "Current:"
# "最佳:" → "Best:"
# "最近 {n} 次实验:" → "Recent {n} experiments:"
# "尚无实验记录" → "No experiments yet"
```

Full replacement for the `print_status` function body — replace lines from `lines = []` to end of function with:

```python
    lines = []
    lines.append(f"[bold]Phase:[/bold] {PHASE_NAMES.get(state['phase'], 'Unknown')}")
    lines.append(f"[bold]Branch:[/bold] {state.get('branch', 'N/A')}")
    lines.append(f"[bold]Mode:[/bold] {state['mode']}")
    lines.append("")

    total = state["total"]
    if total > 0:
        lines.append(
            f"[bold]Experiments:[/bold] {total} total | "
            f"[green]{state['keep']} kept[/green] | "
            f"[yellow]{state['discard']} discarded[/yellow] | "
            f"[red]{state['crash']} crashed[/red]"
        )
        pm = state["primary_metric"]
        direction = state["direction"]
        arrow = "↑" if direction == "higher_is_better" else "↓"
        lines.append(f"[bold]Primary Metric:[/bold] {pm} {arrow}")
        if state["baseline_value"] is not None:
            lines.append(f"  Baseline: {state['baseline_value']:.4f}")
        if state["current_value"] is not None:
            lines.append(f"  Current:  {state['current_value']:.4f}")
        if state["best_value"] is not None:
            lines.append(f"  Best:     {state['best_value']:.4f}")
        lines.append("")

        recent = state["recent"]
        n = len(recent)
        lines.append(f"[bold]Recent {n} experiments:[/bold]")
        for r in recent:
            st = r["status"]
            color = {"keep": "green", "discard": "yellow", "crash": "red"}.get(st, "white")
            lines.append(f"  [{color}][{st}][/{color}] {r['description']}  {r['primary_metric']}={r['metric_value']}")
    else:
        lines.append("[dim]No experiments yet[/dim]")

    panel = Panel("\n".join(lines), title="Open Researcher", border_style="blue")
    Console().print(panel)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_status.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/status_cmd.py tests/test_status.py
git commit -m "refactor: internationalize status output (Chinese → English)"
```

---

### Task 3: Fix Hardcoded Paths in test_record.py

**Files:**
- Modify: `tests/test_record.py`

**Context:** Lines 28 and 76 contain `/Users/shatianming/Downloads/open-researcher/src/open_researcher/scripts/record.py` — this fails on any other machine.

**Step 1: Fix the hardcoded paths**

In `tests/test_record.py`, find the hardcoded path (appears at lines 28 and 76) and replace with a relative path computed from `__file__`:

At the top of the file, add after the existing imports:

```python
RECORD_SCRIPT = Path(__file__).parent.parent / "src" / "open_researcher" / "scripts" / "record.py"
```

Then replace both occurrences of the hardcoded path:
```python
# OLD (line 28 and 76):
Path("/Users/shatianming/Downloads/open-researcher/src/open_researcher/scripts/record.py")
# NEW (both occurrences):
RECORD_SCRIPT
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_record.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_record.py
git commit -m "fix: remove hardcoded absolute path in test_record.py"
```

---

### Task 4: Agent Base Adapter + Registry

**Files:**
- Create: `src/open_researcher/agents/__init__.py`
- Create: `src/open_researcher/agents/base.py`
- Create: `tests/test_agents.py`

**Step 1: Write failing tests for agent base and registry**

Create `tests/test_agents.py`:

```python
"""Tests for agent adapter base class and registry."""

import pytest

from open_researcher.agents.base import AgentAdapter
from open_researcher.agents import get_agent, list_agents, detect_agent


class DummyAgent(AgentAdapter):
    name = "dummy"
    command = "dummy-bin"

    def check_installed(self) -> bool:
        return True

    def build_command(self, program_md, workdir):
        return ["dummy-bin", "--prompt", str(program_md)]

    def run(self, workdir, on_output=None):
        return 0


def test_adapter_interface():
    agent = DummyAgent()
    assert agent.name == "dummy"
    assert agent.check_installed() is True
    cmd = agent.build_command("/tmp/program.md", "/tmp/work")
    assert cmd[0] == "dummy-bin"


def test_list_agents():
    agents = list_agents()
    assert isinstance(agents, dict)
    # Should have at least the built-in adapters
    assert "claude-code" in agents
    assert "codex" in agents
    assert "aider" in agents
    assert "opencode" in agents


def test_get_agent_known():
    agent = get_agent("claude-code")
    assert agent.name == "claude-code"


def test_get_agent_unknown():
    with pytest.raises(KeyError):
        get_agent("nonexistent-agent")


def test_detect_agent_returns_none_when_none_installed(monkeypatch):
    """When no agent binary is found, detect_agent returns None."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda x: None)
    result = detect_agent()
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_agents.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Create the base adapter class**

Create `src/open_researcher/agents/base.py`:

```python
"""Abstract base class for AI agent adapters."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


class AgentAdapter(ABC):
    """Base class that all agent adapters must implement."""

    name: str
    command: str  # binary name to check with shutil.which

    @abstractmethod
    def check_installed(self) -> bool:
        """Return True if the agent binary is available on PATH."""

    @abstractmethod
    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        """Build the subprocess command list to launch the agent."""

    @abstractmethod
    def run(self, workdir: Path, on_output: Callable[[str], None] | None = None) -> int:
        """Launch the agent, stream output via callback, return exit code."""
```

**Step 4: Create the agent registry**

Create `src/open_researcher/agents/__init__.py`:

```python
"""Agent adapter registry — discover, list, and instantiate agents."""

import shutil

from open_researcher.agents.base import AgentAdapter


_REGISTRY: dict[str, type[AgentAdapter]] = {}


def register(cls: type[AgentAdapter]) -> type[AgentAdapter]:
    """Decorator to register an agent adapter class."""
    _REGISTRY[cls.name] = cls
    return cls


def list_agents() -> dict[str, type[AgentAdapter]]:
    """Return all registered agent adapter classes."""
    _ensure_loaded()
    return dict(_REGISTRY)


def get_agent(name: str) -> AgentAdapter:
    """Instantiate an agent adapter by name. Raises KeyError if unknown."""
    _ensure_loaded()
    if name not in _REGISTRY:
        raise KeyError(f"Unknown agent: {name!r}. Available: {', '.join(_REGISTRY)}")
    return _REGISTRY[name]()


def detect_agent() -> AgentAdapter | None:
    """Auto-detect the first installed agent. Returns None if none found."""
    _ensure_loaded()
    preference = ["claude-code", "codex", "aider", "opencode"]
    for agent_name in preference:
        if agent_name in _REGISTRY:
            adapter = _REGISTRY[agent_name]()
            if adapter.check_installed():
                return adapter
    return None


_loaded = False

def _ensure_loaded():
    """Lazy-load all built-in adapters to populate the registry."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Import adapter modules so their @register decorators run
    from open_researcher.agents import claude_code  # noqa: F401
    from open_researcher.agents import codex  # noqa: F401
    from open_researcher.agents import aider  # noqa: F401
    from open_researcher.agents import opencode  # noqa: F401
```

**Step 5: Run tests to verify they fail (adapters not yet created)**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_agents.py::test_adapter_interface -v`
Expected: PASS (DummyAgent is self-contained)

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_agents.py::test_list_agents -v`
Expected: FAIL — adapter modules don't exist yet

**Step 6: Commit base + registry (adapters come in next task)**

```bash
git add src/open_researcher/agents/__init__.py src/open_researcher/agents/base.py tests/test_agents.py
git commit -m "feat: add agent adapter base class and registry"
```

---

### Task 5: Agent Adapters (Claude Code, Codex, Aider, OpenCode)

**Files:**
- Create: `src/open_researcher/agents/claude_code.py`
- Create: `src/open_researcher/agents/codex.py`
- Create: `src/open_researcher/agents/aider.py`
- Create: `src/open_researcher/agents/opencode.py`
- Modify: `tests/test_agents.py`

**Step 1: Add adapter tests**

Append to `tests/test_agents.py`:

```python
def test_claude_code_build_command():
    from open_researcher.agents.claude_code import ClaudeCodeAdapter
    agent = ClaudeCodeAdapter()
    cmd = agent.build_command(Path("/tmp/program.md"), Path("/tmp/work"))
    assert cmd[0] == "claude"
    assert "-p" in cmd


def test_codex_build_command():
    from open_researcher.agents.codex import CodexAdapter
    agent = CodexAdapter()
    cmd = agent.build_command(Path("/tmp/program.md"), Path("/tmp/work"))
    assert cmd[0] == "codex"


def test_aider_build_command():
    from open_researcher.agents.aider import AiderAdapter
    agent = AiderAdapter()
    cmd = agent.build_command(Path("/tmp/program.md"), Path("/tmp/work"))
    assert cmd[0] == "aider"


def test_opencode_build_command():
    from open_researcher.agents.opencode import OpencodeAdapter
    agent = OpencodeAdapter()
    cmd = agent.build_command(Path("/tmp/program.md"), Path("/tmp/work"))
    assert cmd[0] == "opencode"


def test_check_installed_uses_shutil_which(monkeypatch):
    """Adapters use shutil.which to check installation."""
    import shutil
    from open_researcher.agents.claude_code import ClaudeCodeAdapter
    agent = ClaudeCodeAdapter()
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/claude" if x == "claude" else None)
    assert agent.check_installed() is True
    monkeypatch.setattr(shutil, "which", lambda x: None)
    assert agent.check_installed() is False
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_agents.py -v`
Expected: FAIL — ModuleNotFoundError for adapter modules

**Step 3: Create Claude Code adapter**

Create `src/open_researcher/agents/claude_code.py`:

```python
"""Claude Code agent adapter."""

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class ClaudeCodeAdapter(AgentAdapter):
    name = "claude-code"
    command = "claude"

    def check_installed(self) -> bool:
        return shutil.which(self.command) is not None

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        prompt = program_md.read_text()
        return [
            self.command,
            "-p", prompt,
            "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep",
        ]

    def run(self, workdir: Path, on_output: Callable[[str], None] | None = None) -> int:
        program_md = workdir / ".research" / "program.md"
        cmd = self.build_command(program_md, workdir)
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            if on_output:
                on_output(line.rstrip("\n"))
        return proc.wait()
```

**Step 4: Create Codex adapter**

Create `src/open_researcher/agents/codex.py`:

```python
"""Codex CLI agent adapter."""

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class CodexAdapter(AgentAdapter):
    name = "codex"
    command = "codex"

    def check_installed(self) -> bool:
        return shutil.which(self.command) is not None

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        prompt = program_md.read_text()
        return [
            self.command,
            "exec",
            "-c", prompt,
        ]

    def run(self, workdir: Path, on_output: Callable[[str], None] | None = None) -> int:
        program_md = workdir / ".research" / "program.md"
        cmd = self.build_command(program_md, workdir)
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            if on_output:
                on_output(line.rstrip("\n"))
        return proc.wait()
```

**Step 5: Create Aider adapter**

Create `src/open_researcher/agents/aider.py`:

```python
"""Aider agent adapter."""

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class AiderAdapter(AgentAdapter):
    name = "aider"
    command = "aider"

    def check_installed(self) -> bool:
        return shutil.which(self.command) is not None

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        return [
            self.command,
            "--yes-always",
            "--message-file", str(program_md),
        ]

    def run(self, workdir: Path, on_output: Callable[[str], None] | None = None) -> int:
        program_md = workdir / ".research" / "program.md"
        cmd = self.build_command(program_md, workdir)
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            if on_output:
                on_output(line.rstrip("\n"))
        return proc.wait()
```

**Step 6: Create OpenCode adapter**

Create `src/open_researcher/agents/opencode.py`:

```python
"""OpenCode agent adapter."""

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class OpencodeAdapter(AgentAdapter):
    name = "opencode"
    command = "opencode"

    def check_installed(self) -> bool:
        return shutil.which(self.command) is not None

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        prompt = program_md.read_text()
        return [
            self.command,
            "-p", prompt,
        ]

    def run(self, workdir: Path, on_output: Callable[[str], None] | None = None) -> int:
        program_md = workdir / ".research" / "program.md"
        cmd = self.build_command(program_md, workdir)
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            if on_output:
                on_output(line.rstrip("\n"))
        return proc.wait()
```

**Step 7: Run all agent tests**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_agents.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/open_researcher/agents/claude_code.py src/open_researcher/agents/codex.py src/open_researcher/agents/aider.py src/open_researcher/agents/opencode.py tests/test_agents.py
git commit -m "feat: add agent adapters for Claude Code, codex, aider, opencode"
```

---

### Task 6: Run Command with TUI Progress

**Files:**
- Create: `src/open_researcher/run_cmd.py`
- Modify: `src/open_researcher/cli.py`
- Create: `tests/test_run.py`

**Step 1: Write failing tests for run command**

Create `tests/test_run.py`:

```python
"""Tests for the run command."""

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _setup_research_dir(repo: Path):
    """Create a minimal .research/ directory for testing."""
    research = repo / ".research"
    research.mkdir()
    (research / "program.md").write_text("Test program instructions")
    (research / "config.yaml").write_text(
        "mode: autonomous\nmetrics:\n  primary:\n    name: accuracy\n    direction: higher_is_better\n"
    )
    (research / "results.tsv").write_text(
        "timestamp\tcommit\tprimary_metric\tmetric_value\tsecondary_metrics\tstatus\tdescription\n"
    )
    (research / "project-understanding.md").write_text("# Project\n")
    (research / "evaluation.md").write_text("# Evaluation\n")
    scripts = research / "scripts"
    scripts.mkdir()
    (scripts / "record.py").write_text("")
    (scripts / "rollback.sh").write_text("")
    return repo


def test_run_fails_without_research_dir():
    from open_researcher.run_cmd import do_run

    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(SystemExit):
            do_run(Path(tmp), agent_name=None, dry_run=False)


def test_run_fails_when_no_agent_found():
    from open_researcher.run_cmd import do_run

    with tempfile.TemporaryDirectory() as tmp:
        _setup_research_dir(Path(tmp))
        with patch("open_researcher.run_cmd.detect_agent", return_value=None), \
             pytest.raises(SystemExit):
            do_run(Path(tmp), agent_name=None, dry_run=False)


def test_run_dry_run_prints_command(capsys):
    from open_researcher.run_cmd import do_run

    with tempfile.TemporaryDirectory() as tmp:
        repo = _setup_research_dir(Path(tmp))
        mock_agent = MagicMock()
        mock_agent.name = "test-agent"
        mock_agent.build_command.return_value = ["test-cmd", "--flag"]

        with patch("open_researcher.run_cmd.get_agent", return_value=mock_agent), \
             patch("open_researcher.run_cmd.detect_agent", return_value=mock_agent):
            do_run(repo, agent_name="test-agent", dry_run=True)

        captured = capsys.readouterr()
        assert "test-cmd" in captured.out


def test_run_launches_agent():
    from open_researcher.run_cmd import do_run

    with tempfile.TemporaryDirectory() as tmp:
        repo = _setup_research_dir(Path(tmp))
        mock_agent = MagicMock()
        mock_agent.name = "test-agent"
        mock_agent.run.return_value = 0

        with patch("open_researcher.run_cmd.get_agent", return_value=mock_agent):
            do_run(repo, agent_name="test-agent", dry_run=False)

        mock_agent.run.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_run.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Implement run_cmd.py**

Create `src/open_researcher/run_cmd.py`:

```python
"""Run command — launch an AI agent to execute the research workflow."""

import sys
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from open_researcher.agents import detect_agent, get_agent
from open_researcher.status_cmd import parse_research_state

console = Console()

# Keep last N lines of agent output for TUI display
_MAX_OUTPUT_LINES = 15


def _build_stats_panel(repo_path: Path) -> Panel:
    """Build the top panel showing experiment statistics."""
    try:
        state = parse_research_state(repo_path)
    except Exception:
        return Panel("[dim]Waiting for data...[/dim]", title="Stats")

    from open_researcher.status_cmd import PHASE_NAMES

    lines = []
    phase = state.get("phase", 1)
    lines.append(f"[bold]Phase:[/bold] {PHASE_NAMES.get(phase, 'Unknown')}")
    lines.append(f"[bold]Branch:[/bold] {state.get('branch', 'N/A')}    [bold]Mode:[/bold] {state.get('mode', 'N/A')}")

    total = state.get("total", 0)
    if total > 0:
        lines.append(
            f"[bold]Experiments:[/bold] {total} total | "
            f"[green]{state['keep']} kept[/green] | "
            f"[yellow]{state['discard']} discarded[/yellow] | "
            f"[red]{state['crash']} crashed[/red]"
        )
        pm = state.get("primary_metric", "")
        direction = state.get("direction", "")
        arrow = "↑" if direction == "higher_is_better" else "↓"
        lines.append(f"[bold]Primary Metric:[/bold] {pm} {arrow}")
        if state.get("baseline_value") is not None:
            lines.append(f"  Baseline: {state['baseline_value']:.4f}   Current: {state.get('current_value', 0):.4f}   Best: {state.get('best_value', 0):.4f}")

        recent = state.get("recent", [])
        if recent:
            lines.append("")
            for r in recent[-5:]:
                st = r["status"]
                color = {"keep": "green", "discard": "yellow", "crash": "red"}.get(st, "white")
                lines.append(f"  [{color}][{st}][/{color}] {r['description']}  {r['primary_metric']}={r['metric_value']}")
    else:
        lines.append("[dim]No experiments yet — agent is starting...[/dim]")

    return Panel("\n".join(lines), title="Open Researcher", border_style="blue")


def _build_output_panel(output_lines: list[str], agent_name: str) -> Panel:
    """Build the bottom panel showing agent stdout."""
    text = "\n".join(output_lines[-_MAX_OUTPUT_LINES:]) if output_lines else "[dim]Waiting for agent output...[/dim]"
    return Panel(text, title=f"Agent: {agent_name}", border_style="green")


def do_run(repo_path: Path, agent_name: str | None, dry_run: bool) -> None:
    """Execute the research workflow using an AI agent."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    program_md = research / "program.md"
    if not program_md.exists():
        console.print("[red]Error:[/red] .research/program.md not found.")
        raise SystemExit(1)

    # Resolve agent
    if agent_name:
        try:
            agent = get_agent(agent_name)
        except KeyError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise SystemExit(1)
    else:
        agent = detect_agent()
        if agent is None:
            console.print(
                "[red]Error:[/red] No supported AI agent found.\n"
                "Install one of: claude (Claude Code), codex, aider, opencode\n"
                "Or specify with: open-researcher run --agent <name>"
            )
            raise SystemExit(1)
        console.print(f"[green]Auto-detected agent:[/green] {agent.name}")

    # Dry run — just show the command
    if dry_run:
        cmd = agent.build_command(program_md, repo_path)
        console.print(f"[bold]Agent:[/bold] {agent.name}")
        console.print(f"[bold]Command:[/bold] {' '.join(cmd[:3])}...")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run — no agent launched.[/dim]")
        return

    # Launch agent with TUI
    console.print(f"[green]Launching {agent.name}...[/green]")
    output_lines: list[str] = []
    agent_done = threading.Event()
    exit_code = 0

    def _run_agent():
        nonlocal exit_code

        def on_output(line: str):
            output_lines.append(line)
            # Also write to run.log
            log_path = research / "run.log"
            with open(log_path, "a") as f:
                f.write(line + "\n")

        exit_code = agent.run(repo_path, on_output=on_output)
        agent_done.set()

    agent_thread = threading.Thread(target=_run_agent, daemon=True)
    agent_thread.start()

    try:
        with Live(console=console, refresh_per_second=1, transient=True) as live:
            while not agent_done.is_set():
                layout = Layout()
                layout.split_column(
                    Layout(name="stats", ratio=2),
                    Layout(name="output", ratio=1),
                )
                layout["stats"].update(_build_stats_panel(repo_path))
                layout["output"].update(_build_output_panel(output_lines, agent.name))
                live.update(layout)
                agent_done.wait(timeout=1.0)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        raise SystemExit(130)

    agent_thread.join(timeout=5)

    if exit_code == 0:
        console.print(f"\n[green]Agent {agent.name} completed successfully.[/green]")
    else:
        console.print(f"\n[red]Agent {agent.name} exited with code {exit_code}.[/red]")

    # Print final status
    from open_researcher.status_cmd import print_status
    print_status(repo_path)
```

**Step 4: Add `run` command to cli.py**

In `src/open_researcher/cli.py`, add the `run` command. Insert after the existing `export` command:

```python
@app.command()
def run(
    agent: str = typer.Option(None, help="Agent to use (claude-code, codex, aider, opencode). Auto-detects if omitted."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the command without executing."),
):
    """Launch an AI agent to run the research workflow."""
    from open_researcher.run_cmd import do_run

    do_run(repo_path=Path.cwd(), agent_name=agent, dry_run=dry_run)
```

**Step 5: Run all tests**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_run.py -v`
Expected: ALL PASS

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/open_researcher/run_cmd.py src/open_researcher/cli.py tests/test_run.py
git commit -m "feat: add 'run' command with agent integration and real-time TUI progress"
```

---

### Task 7: CLI-Level Tests

**Files:**
- Create: `tests/test_cli.py`

**Step 1: Write CLI tests using Typer CliRunner**

Create `tests/test_cli.py`:

```python
"""Tests for the CLI entry point."""

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from open_researcher.cli import app

runner = CliRunner()


def test_init_via_cli():
    with runner.isolated_filesystem():
        # Create a fake git repo so init works
        Path(".git").mkdir()
        result = runner.invoke(app, ["init", "--tag", "test1"])
        assert result.exit_code == 0
        assert Path(".research").is_dir()
        assert Path(".research/program.md").exists()


def test_init_refuses_duplicate():
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        Path(".research").mkdir()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1


def test_status_without_research():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1


def test_results_without_research():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["results"])
        assert result.exit_code == 1


def test_export_without_research():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 1


def test_run_without_research():
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 1


def test_run_dry_run(monkeypatch):
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        result = runner.invoke(app, ["init", "--tag", "clitest"])
        assert result.exit_code == 0

        # Mock agent detection
        from unittest.mock import MagicMock, patch
        mock_agent = MagicMock()
        mock_agent.name = "mock-agent"
        mock_agent.build_command.return_value = ["mock-cmd", "--test"]

        with patch("open_researcher.run_cmd.detect_agent", return_value=mock_agent):
            result = runner.invoke(app, ["run", "--dry-run"])
            assert result.exit_code == 0
            assert "mock-cmd" in result.stdout
```

**Step 2: Run tests**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: add CLI-level tests with Typer CliRunner"
```

---

### Task 8: README.md

**Files:**
- Create: `README.md`

**Step 1: Create README.md**

Create `README.md`:

````markdown
# Open Researcher 🔬

> **Let AI agents run experiments in any repo while you sleep.**

Open Researcher is a CLI framework that sets up automated research workflows in any git repository. Point it at your project, pick an AI agent, and let it autonomously understand your code, design evaluation metrics, establish baselines, and run experiments — keeping what works, discarding what doesn't.

Unlike tools locked to specific repo formats, Open Researcher works with **any** project — ML training, performance optimization, algorithm design, or anything with measurable outcomes.

## Quick Start

```bash
pip install open-researcher

cd your-project
open-researcher init
open-researcher run --agent claude-code
# Go to sleep. Check results in the morning:
open-researcher status
```

## How It Works

Open Researcher generates a `.research/` directory in your repo with:

| File | Purpose |
|------|---------|
| `program.md` | Agent instructions — the 4-phase research workflow |
| `config.yaml` | Mode (autonomous/collaborative), metrics, timeout |
| `project-understanding.md` | Agent fills this: what the project does |
| `evaluation.md` | Agent fills this: how to measure improvement |
| `results.tsv` | Experiment log (timestamp, commit, metrics, status) |
| `scripts/record.py` | Record experiment results |
| `scripts/rollback.sh` | Discard failed experiments |

### The 4-Phase Workflow

1. **Understand Project** — Agent reads your code, docs, tests. Writes `project-understanding.md`.
2. **Design Evaluation** — Agent defines metrics (what to optimize, how to measure). Writes `evaluation.md`.
3. **Establish Baseline** — Run current code, record baseline metrics.
4. **Experiment Loop** — Propose idea → implement → test → evaluate → keep or discard. Repeat.

Each experiment is a git commit. Successful experiments stay; failed ones are rolled back. Everything is logged in `results.tsv`.

## Supported Agents

| Agent | Command | Status |
|-------|---------|--------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `--agent claude-code` | ✅ Supported |
| [Codex CLI](https://github.com/openai/codex) | `--agent codex` | ✅ Supported |
| [Aider](https://github.com/paul-gauthier/aider) | `--agent aider` | ✅ Supported |
| [OpenCode](https://github.com/opencode-ai/opencode) | `--agent opencode` | ✅ Supported |

Auto-detection: If you don't specify `--agent`, Open Researcher will find the first installed agent.

## Commands

```bash
open-researcher init [--tag NAME]           # Initialize .research/ directory
open-researcher run [--agent NAME] [--dry-run]  # Launch AI agent
open-researcher status                      # Show experiment progress
open-researcher results                     # Print results table
open-researcher export                      # Export markdown report
open-researcher dashboard [--port 8384]     # Launch web dashboard
```

## Web Dashboard

```bash
open-researcher dashboard
# Open http://localhost:8384
```

Dark-themed dashboard with:
- Real-time experiment statistics
- Metric trend chart (Chart.js)
- Experiment history table
- Document viewer (project understanding, evaluation design)

## Comparison with autoresearch

| Feature | autoresearch | Open Researcher |
|---------|-------------|-----------------|
| Works with any repo | ❌ Fixed 3-file format | ✅ Any git repo |
| Agent support | Claude Code only | Claude Code, Codex, Aider, OpenCode |
| Auto project understanding | ❌ Manual | ✅ Agent-driven |
| Auto evaluation design | ❌ Manual | ✅ Agent-driven |
| Real-time TUI progress | ❌ | ✅ Rich live display |
| Web dashboard | ❌ | ✅ Built-in |
| Intervention modes | Autonomous only | Autonomous + Collaborative |
| `pip install` | ❌ | ✅ |

## Configuration

Edit `.research/config.yaml`:

```yaml
mode: autonomous          # autonomous | collaborative
experiment:
  timeout: 600            # seconds per experiment
  max_consecutive_crashes: 3
metrics:
  primary:
    name: ""              # filled by agent (e.g., "test_acc")
    direction: ""         # higher_is_better | lower_is_better
environment: |
  # Describe your execution environment
  # e.g., Python 3.11, CUDA 12.1, 1x A100
```

## Examples

See [`examples/`](examples/) for complete demo setups:

- **Triton Kernel Optimization** — Optimize GPU kernels in [Liger-Kernel](https://github.com/linkedin/Liger-Kernel)
- **NLP Model Training** — Improve [nanoGPT](https://github.com/karpathy/nanoGPT) validation loss
- **ML Fine-tuning** — Optimize HuggingFace Transformers GLUE benchmark

## Development

```bash
git clone https://github.com/open-researcher/open-researcher.git
cd open-researcher
make dev    # install with dev dependencies
make test   # run tests
make lint   # run linter
```

## License

MIT — see [LICENSE](LICENSE).
````

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add comprehensive README with quick start and feature comparison"
```

---

### Task 9: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Create CI workflow**

```bash
mkdir -p .github/workflows
```

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint
        run: ruff check src/ tests/

      - name: Test
        run: pytest tests/ -v
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for lint + test on Python 3.10-3.13"
```

---

### Task 10: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

**Step 1: Create CONTRIBUTING.md**

Create `CONTRIBUTING.md`:

```markdown
# Contributing to Open Researcher

Thanks for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/open-researcher/open-researcher.git
cd open-researcher
python -m venv .venv
source .venv/bin/activate
make dev
```

## Running Tests

```bash
make test
```

## Code Style

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
make lint    # check
make format  # auto-fix
```

## Adding a New Agent Adapter

1. Create `src/open_researcher/agents/your_agent.py`
2. Implement the `AgentAdapter` interface (see `base.py`)
3. Add the `@register` decorator
4. Add tests in `tests/test_agents.py`
5. Update the agent table in `README.md`

## Pull Requests

- One feature per PR
- Include tests
- Run `make lint && make test` before submitting
```

**Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING.md"
```

---

### Task 11: Demo Case — nanoGPT Example

**Files:**
- Create: `examples/nanogpt/README.md`
- Create: `examples/nanogpt/.research/config.yaml`
- Create: `examples/nanogpt/.research/program.md`
- Create: `examples/nanogpt/.research/project-understanding.md`
- Create: `examples/nanogpt/.research/evaluation.md`
- Create: `examples/nanogpt/.research/results-sample.tsv`

**Context:** This is a pre-configured example showing how Open Researcher works with karpathy/nanoGPT. Users can clone nanoGPT, copy this `.research/` directory in, and run `open-researcher run`.

**Step 1: Create the example directory structure**

```bash
mkdir -p examples/nanogpt/.research/scripts
```

**Step 2: Create example README**

Create `examples/nanogpt/README.md`:

````markdown
# Example: nanoGPT Research

This example shows how to use Open Researcher with [karpathy/nanoGPT](https://github.com/karpathy/nanoGPT) to automatically improve language model training.

## Setup

```bash
# Clone nanoGPT
git clone https://github.com/karpathy/nanoGPT.git
cd nanoGPT
pip install -r requirements.txt

# Prepare data
python data/shakespeare_char/prepare.py

# Initialize Open Researcher (or copy the pre-configured .research/)
open-researcher init --tag nanogpt

# Launch research
open-researcher run --agent claude-code
```

## What the Agent Will Try

- Learning rate schedules (cosine, linear warmup)
- Model architecture changes (layers, heads, embedding dim)
- Regularization (dropout, weight decay tuning)
- Training optimizations (gradient accumulation, mixed precision)
- Data preprocessing improvements

## Metrics

- **Primary:** `val_loss` (lower is better)
- **Evaluation:** Run `python train.py` with reduced iterations, extract final val_loss

## Sample Results

See `results-sample.tsv` for example experiment outcomes.
````

**Step 3: Create pre-configured .research/ files**

Create `examples/nanogpt/.research/config.yaml`:

```yaml
mode: autonomous
experiment:
  timeout: 600
  max_consecutive_crashes: 3
metrics:
  primary:
    name: val_loss
    direction: lower_is_better
environment: |
  Python 3.10+, PyTorch 2.0+
  GPU recommended but CPU works for Shakespeare char-level
  Dataset: Shakespeare char-level (data/shakespeare_char/)
```

Create `examples/nanogpt/.research/project-understanding.md`:

```markdown
# Project Understanding

## Project Goal
nanoGPT is a minimal GPT implementation for training and fine-tuning medium-sized language models. It focuses on simplicity and readability while being performant enough for real experiments.

## Code Structure
- `train.py` — Main training script (single file, ~300 lines)
- `model.py` — GPT model definition (transformer architecture)
- `config/` — Training configurations for different datasets/scales
- `data/` — Dataset preparation scripts (Shakespeare, OpenWebText)
- `sample.py` — Text generation from trained model

## How to Run
```bash
python train.py config/train_shakespeare_char.py
```

## Key Configuration
- `n_layer`, `n_head`, `n_embd` — Model size
- `learning_rate`, `max_iters`, `lr_decay_iters` — Training schedule
- `dropout`, `weight_decay` — Regularization
- `batch_size`, `block_size` — Data loading
```

Create `examples/nanogpt/.research/evaluation.md`:

```markdown
# Evaluation Design

## Primary Metric
- **Name:** val_loss
- **Direction:** lower_is_better
- **How to measure:** Run `python train.py config/train_shakespeare_char.py` with `--max_iters=500 --eval_interval=500`. Extract the final `val loss` from stdout.

## Evaluation Command
```bash
python train.py config/train_shakespeare_char.py \
  --max_iters=500 --eval_interval=500 --eval_iters=20 2>&1 | \
  grep "val loss" | tail -1 | awk '{print $NF}'
```

## Secondary Metrics
- `train_loss` — Training loss at evaluation time
- `tokens_per_sec` — Training throughput

## Baseline Method
Run the unmodified training script with default Shakespeare char config for 500 iterations.
```

Create `examples/nanogpt/.research/results-sample.tsv`:

```
timestamp	commit	primary_metric	metric_value	secondary_metrics	status	description
2026-03-09T10:00:00Z	a1b2c3d	val_loss	1.520000	{"train_loss": 1.480}	keep	baseline: default shakespeare char config
2026-03-09T10:15:00Z	e4f5g6h	val_loss	1.495000	{"train_loss": 1.450}	keep	cosine lr schedule with warmup
2026-03-09T10:30:00Z	i7j8k9l	val_loss	1.550000	{"train_loss": 1.510}	discard	increased dropout to 0.3 (too aggressive)
2026-03-09T10:45:00Z	m0n1o2p	val_loss	1.470000	{"train_loss": 1.420}	keep	added gradient clipping + weight decay tuning
2026-03-09T11:00:00Z	q3r4s5t	val_loss	1.480000	{"train_loss": 1.440}	discard	doubled n_head (marginal, not worth complexity)
```

**Step 4: Commit**

```bash
git add examples/
git commit -m "docs: add nanoGPT demo example with pre-configured .research/"
```

---

### Task 12: Demo Case — Liger-Kernel Example

**Files:**
- Create: `examples/liger-kernel/README.md`
- Create: `examples/liger-kernel/.research/config.yaml`
- Create: `examples/liger-kernel/.research/project-understanding.md`
- Create: `examples/liger-kernel/.research/evaluation.md`
- Create: `examples/liger-kernel/.research/results-sample.tsv`

**Step 1: Create directory**

```bash
mkdir -p examples/liger-kernel/.research/scripts
```

**Step 2: Create files**

Create `examples/liger-kernel/README.md`:

````markdown
# Example: Liger-Kernel Research

This example shows how to use Open Researcher with [linkedin/Liger-Kernel](https://github.com/linkedin/Liger-Kernel) to optimize Triton GPU kernels for LLM training.

## Setup

```bash
git clone https://github.com/linkedin/Liger-Kernel.git
cd Liger-Kernel
pip install -e ".[dev]"

# Initialize Open Researcher
open-researcher init --tag liger

# Launch research
open-researcher run --agent claude-code
```

## Metrics

- **Primary:** `speedup_ratio` (higher is better) — execution speed vs PyTorch baseline
- **Evaluation:** Run kernel benchmarks, compare Triton kernel throughput against PyTorch reference
````

Create `examples/liger-kernel/.research/config.yaml`:

```yaml
mode: autonomous
experiment:
  timeout: 900
  max_consecutive_crashes: 3
metrics:
  primary:
    name: speedup_ratio
    direction: higher_is_better
environment: |
  Python 3.10+, PyTorch 2.0+, Triton
  GPU required (CUDA)
  Benchmark suite: built-in Liger-Kernel benchmarks
```

Create `examples/liger-kernel/.research/project-understanding.md`:

```markdown
# Project Understanding

## Project Goal
Liger-Kernel provides efficient Triton kernels for LLM training operations (RMSNorm, RoPE, SwiGLU, CrossEntropy, FusedLinearCrossEntropy). Each kernel replaces a PyTorch operation with a faster Triton implementation.

## Code Structure
- `src/liger_kernel/ops/` — Individual Triton kernel implementations
- `src/liger_kernel/transformers/` — Drop-in replacements for HuggingFace layers
- `benchmark/` — Performance benchmarks comparing Triton vs PyTorch
- `test/` — Correctness tests for each kernel

## How to Benchmark
```bash
python benchmark/benchmark_rms_norm.py
```
```

Create `examples/liger-kernel/.research/evaluation.md`:

```markdown
# Evaluation Design

## Primary Metric
- **Name:** speedup_ratio
- **Direction:** higher_is_better
- **How to measure:** Run kernel benchmark, compute ratio of PyTorch time / Triton time

## Evaluation Command
```bash
python benchmark/benchmark_rms_norm.py 2>&1 | grep "speedup" | awk '{print $NF}'
```

## Secondary Metrics
- `memory_savings_pct` — Memory reduction vs PyTorch baseline
- `numerical_error` — Max absolute difference from PyTorch output (must stay < 1e-5)
```

Create `examples/liger-kernel/.research/results-sample.tsv`:

```
timestamp	commit	primary_metric	metric_value	secondary_metrics	status	description
2026-03-09T14:00:00Z	a1b2c3d	speedup_ratio	1.800000	{"memory_savings_pct": 15.2}	keep	baseline: current RMSNorm kernel
2026-03-09T14:20:00Z	e4f5g6h	speedup_ratio	2.100000	{"memory_savings_pct": 18.5}	keep	improved tiling strategy for RMSNorm
2026-03-09T14:40:00Z	i7j8k9l	speedup_ratio	1.600000	{"memory_savings_pct": 12.0}	discard	vectorized load (register pressure too high)
2026-03-09T15:00:00Z	m0n1o2p	speedup_ratio	2.300000	{"memory_savings_pct": 22.1}	keep	fused elementwise + reduction pass
```

**Step 3: Commit**

```bash
git add examples/liger-kernel/
git commit -m "docs: add Liger-Kernel Triton optimization demo example"
```

---

### Task 13: Demo Case — HuggingFace GLUE Fine-tuning

**Files:**
- Create: `examples/hf-glue/README.md`
- Create: `examples/hf-glue/.research/config.yaml`
- Create: `examples/hf-glue/.research/project-understanding.md`
- Create: `examples/hf-glue/.research/evaluation.md`
- Create: `examples/hf-glue/.research/results-sample.tsv`

**Step 1: Create directory**

```bash
mkdir -p examples/hf-glue/.research/scripts
```

**Step 2: Create files**

Create `examples/hf-glue/README.md`:

````markdown
# Example: HuggingFace GLUE Fine-tuning Research

This example shows how to use Open Researcher with HuggingFace Transformers to optimize GLUE benchmark fine-tuning (SST-2 sentiment classification).

## Setup

```bash
git clone https://github.com/huggingface/transformers.git
cd transformers
pip install -e ".[torch]"
pip install datasets evaluate accelerate

# Initialize Open Researcher
open-researcher init --tag glue

# Launch research
open-researcher run --agent claude-code
```

## Metrics

- **Primary:** `eval_accuracy` (higher is better) on SST-2 validation set
- **Evaluation:** Run `examples/pytorch/text-classification/run_glue.py` with reduced epochs
````

Create `examples/hf-glue/.research/config.yaml`:

```yaml
mode: autonomous
experiment:
  timeout: 1200
  max_consecutive_crashes: 3
metrics:
  primary:
    name: eval_accuracy
    direction: higher_is_better
environment: |
  Python 3.10+, PyTorch 2.0+, HuggingFace Transformers
  GPU recommended (A10G or better for reasonable speed)
  Dataset: SST-2 from GLUE benchmark (auto-downloaded)
```

Create `examples/hf-glue/.research/project-understanding.md`:

```markdown
# Project Understanding

## Project Goal
HuggingFace Transformers is the most popular library for NLP model training and inference. This research focuses on optimizing SST-2 (Stanford Sentiment Treebank) fine-tuning — a binary sentiment classification task.

## Code Structure
- `examples/pytorch/text-classification/run_glue.py` — Main GLUE fine-tuning script
- `src/transformers/models/` — Model implementations (BERT, RoBERTa, etc.)
- `src/transformers/trainer.py` — Training loop
- `src/transformers/optimization.py` — Learning rate schedules

## How to Run
```bash
python examples/pytorch/text-classification/run_glue.py \
  --model_name_or_path bert-base-uncased \
  --task_name sst2 \
  --do_train --do_eval \
  --max_seq_length 128 \
  --per_device_train_batch_size 32 \
  --learning_rate 2e-5 \
  --num_train_epochs 1 \
  --output_dir /tmp/sst2
```
```

Create `examples/hf-glue/.research/evaluation.md`:

```markdown
# Evaluation Design

## Primary Metric
- **Name:** eval_accuracy
- **Direction:** higher_is_better
- **How to measure:** Run fine-tuning script with `--do_eval`, extract `eval_accuracy` from trainer output

## Evaluation Command
```bash
python examples/pytorch/text-classification/run_glue.py \
  --model_name_or_path bert-base-uncased \
  --task_name sst2 \
  --do_train --do_eval \
  --max_seq_length 128 \
  --per_device_train_batch_size 32 \
  --learning_rate 2e-5 \
  --num_train_epochs 1 \
  --output_dir /tmp/sst2-eval 2>&1 | \
  grep "eval_accuracy" | tail -1
```

## Secondary Metrics
- `eval_loss` — Validation loss
- `train_runtime` — Training time in seconds
- `train_samples_per_second` — Training throughput
```

Create `examples/hf-glue/.research/results-sample.tsv`:

```
timestamp	commit	primary_metric	metric_value	secondary_metrics	status	description
2026-03-09T16:00:00Z	a1b2c3d	eval_accuracy	0.920000	{"eval_loss": 0.312, "train_runtime": 180}	keep	baseline: bert-base-uncased default config
2026-03-09T16:30:00Z	e4f5g6h	eval_accuracy	0.928000	{"eval_loss": 0.298, "train_runtime": 185}	keep	linear warmup 10% + cosine decay
2026-03-09T17:00:00Z	i7j8k9l	eval_accuracy	0.915000	{"eval_loss": 0.340, "train_runtime": 175}	discard	reduced max_seq_length to 64 (accuracy drop)
2026-03-09T17:30:00Z	m0n1o2p	eval_accuracy	0.935000	{"eval_loss": 0.275, "train_runtime": 195}	keep	switched to roberta-base + lr 1e-5
2026-03-09T18:00:00Z	q3r4s5t	eval_accuracy	0.932000	{"eval_loss": 0.280, "train_runtime": 200}	discard	added label smoothing 0.1 (marginal)
```

**Step 3: Commit**

```bash
git add examples/hf-glue/
git commit -m "docs: add HuggingFace GLUE fine-tuning demo example"
```

---

### Task 14: Run Full Test Suite + Lint

**Step 1: Run all tests**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/ -v`
Expected: ALL PASS (should be ~25+ tests now)

**Step 2: Install and run ruff**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pip install ruff && .venv/bin/ruff check src/ tests/`

**Step 3: Fix any lint issues**

Apply ruff fixes: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/ruff check --fix src/ tests/ && .venv/bin/ruff format src/ tests/`

**Step 4: Run tests again after fixes**

Run: `cd /Users/shatianming/Downloads/open-researcher && .venv/bin/pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: fix lint issues and format code with ruff"
```

---

### Task 15: End-to-End Verification

**Step 1: Verify pip install works**

Run:
```bash
cd /Users/shatianming/Downloads/open-researcher
.venv/bin/pip install -e ".[dev]"
```

**Step 2: Verify CLI help**

Run:
```bash
.venv/bin/open-researcher --help
.venv/bin/open-researcher init --help
.venv/bin/open-researcher run --help
.venv/bin/open-researcher status --help
```

Expected: Clean help output for all commands, including the new `run` command.

**Step 3: Verify init + dry-run workflow in a temp repo**

```bash
cd /tmp && mkdir test-or && cd test-or && git init
open-researcher init --tag test
open-researcher run --dry-run
open-researcher status
```

**Step 4: Final commit if any changes**

```bash
git add -A
git commit -m "chore: final verification and cleanup"
```
