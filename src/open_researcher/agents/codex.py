"""Codex CLI agent adapter."""

from pathlib import Path
from typing import Callable

from open_researcher.agents import register
from open_researcher.agents.base import AgentAdapter


@register
class CodexAdapter(AgentAdapter):
    name = "codex"
    command = "codex"

    def build_command(self, program_md: Path, workdir: Path) -> list[str]:
        return [self.command, "exec", "-m", "gpt-5.3-codex", "--full-auto", "-"]

    def run(
        self,
        workdir: Path,
        on_output: Callable[[str], None] | None = None,
        program_file: str = "program.md",
        env: dict[str, str] | None = None,
    ) -> int:
        program_md = workdir / ".research" / program_file
        cmd = self.build_command(program_md, workdir)
        try:
            prompt = program_md.read_text()
        except FileNotFoundError:
            msg = f"[codex] program file not found: {program_md}"
            if on_output:
                on_output(msg)
            return 1
        return self._run_process(cmd, workdir, on_output, stdin_text=prompt, env=env)
