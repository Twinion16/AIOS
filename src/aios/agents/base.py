from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from ..reporting import CONTRACT_TEXT


class BaseAgent(ABC):
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config

    # ------------------------------------------------------------- resolution
    @property
    def executable(self) -> str:
        """Executable from config `agents.<name>.executable` (registry aware),
        falling back to the legacy `agent_paths` section.

        Placeholders: `{root}` = AIOS repository root, plus shell-style
        `~` and environment variables - keeps configs machine-independent.
        """
        import os

        agents_cfg = self.config.get("agents") or {}
        if self.name in agents_cfg and agents_cfg[self.name].get("executable"):
            exe = agents_cfg[self.name]["executable"]
        else:
            legacy = self.config.get("agent_paths") or {}
            exe = legacy.get(self.name, self.name)
        root = self.config.get("_aios_root")
        if root:
            exe = exe.replace("{root}", root)
        return os.path.expandvars(os.path.expanduser(exe))

    def executable_argv(self) -> list:
        r"""argv prefix for this agent.

        Supports multi-token entries such as `python C:\path\wrapper.py`,
        which keeps argument passing inside python.exe (no cmd.exe re-parse
        of prompts containing quotes/`<`/`>`).
        """
        exe = self.executable
        if " " in exe:
            import shlex
            return shlex.split(exe, posix=False)
        return [exe]

    def prompt_for(self, task_context: Dict[str, Any]) -> str:
        """Rendered prompt from the ContextEngine, else a legacy built-in."""
        prompt = task_context.get("prompt")
        if not prompt:
            prompt = self.legacy_prompt(task_context)
        return prompt.rstrip() + "\n\n" + CONTRACT_TEXT

    @abstractmethod
    def legacy_prompt(self, task_context: Dict[str, Any]) -> str:
        """Fallback prompt when no ContextEngine prompt was supplied."""

    def working_dir(self, task_context: Dict[str, Any]) -> Path:
        """Repository for code work; state dir when no repository is set."""
        return Path(task_context.get("cwd") or task_context["project_dir"])

    def write_prompt_file(self, project_dir: Path, content: str) -> Path:
        runs = Path(project_dir) / "Runs"
        runs.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = runs / f"{ts}-{self.name}-prompt.md"
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def result_dict(result) -> Dict[str, Any]:
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    @abstractmethod
    def run(self, task_context: Dict[str, Any]) -> Dict[str, Any]:
        pass
