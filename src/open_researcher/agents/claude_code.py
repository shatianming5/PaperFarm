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
        return [self.command, "-p", prompt, "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep"]

    def run(
        self,
        workdir: Path,
        on_output: Callable[[str], None] | None = None,
        program_file: str = "program.md",
    ) -> int:
        program_md = workdir / ".research" / program_file
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
