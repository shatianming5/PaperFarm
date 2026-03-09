"""Tests for agent adapter base class and registry."""

import shutil
import tempfile
from pathlib import Path

import pytest

from open_researcher.agents import detect_agent, get_agent, list_agents
from open_researcher.agents.base import AgentAdapter


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
    cmd = agent.build_command(Path("/tmp/program.md"), Path("/tmp/work"))
    assert cmd[0] == "dummy-bin"


def test_list_agents():
    agents = list_agents()
    assert isinstance(agents, dict)
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
    monkeypatch.setattr(shutil, "which", lambda x: None)
    result = detect_agent()
    assert result is None


def test_claude_code_build_command():
    from open_researcher.agents.claude_code import ClaudeCodeAdapter

    agent = ClaudeCodeAdapter()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("test prompt")
        f.flush()
        cmd = agent.build_command(Path(f.name), Path("/tmp/work"))
    assert cmd[0] == "claude"
    assert "-p" in cmd


def test_codex_build_command():
    from open_researcher.agents.codex import CodexAdapter

    agent = CodexAdapter()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("test prompt")
        f.flush()
        cmd = agent.build_command(Path(f.name), Path("/tmp/work"))
    assert cmd[0] == "codex"


def test_aider_build_command():
    from open_researcher.agents.aider import AiderAdapter

    agent = AiderAdapter()
    cmd = agent.build_command(Path("/tmp/program.md"), Path("/tmp/work"))
    assert cmd[0] == "aider"


def test_opencode_build_command():
    from open_researcher.agents.opencode import OpencodeAdapter

    agent = OpencodeAdapter()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("test prompt")
        f.flush()
        cmd = agent.build_command(Path(f.name), Path("/tmp/work"))
    assert cmd[0] == "opencode"


def test_check_installed_uses_shutil_which(monkeypatch):
    from open_researcher.agents.claude_code import ClaudeCodeAdapter

    agent = ClaudeCodeAdapter()
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/claude" if x == "claude" else None)
    assert agent.check_installed() is True
    monkeypatch.setattr(shutil, "which", lambda x: None)
    assert agent.check_installed() is False
