"""Claude Code agent adapter."""

from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class ClaudeCodeAdapter(AgentAdapter):
    name = "claude-code"
    command = "claude"

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        return [self.command, "-p", "<prompt>", "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep"]

    def run(
        self,
        workdir: Path,
        on_output: Callable[[str], None] | None = None,
        program_file: str = "program.md",
        env: dict[str, str] | None = None,
    ) -> int:
        program_md = workdir / ".research" / program_file
        try:
            prompt = program_md.read_text()
        except FileNotFoundError:
            msg = f"[claude-code] program file not found: {program_md}"
            if on_output:
                on_output(msg)
            return 1
        cmd = [self.command, "-p", prompt, "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep"]
        return self._run_process(cmd, workdir, on_output, env=env)
