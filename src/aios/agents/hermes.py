from pathlib import Path
from .base import BaseAgent
from ..execution.process import run_command


class HermesAgent(BaseAgent):
    def __init__(self, config):
        super().__init__("hermes", config)

    def legacy_prompt(self, task_context) -> str:
        return """You are the REVIEW agent for AIOS.

Read PROJECT.md, TASK.md, CURRENT_STATE.md, HANDOFF.md and the actual files.
Do NOT assume the implementation is correct. Verify claims against real files.

Write REVIEW.md with findings and a final status of exactly one of:
PASS, FAIL, NEEDS_HUMAN_REVIEW.
"""

    def run(self, task_context):
        project_dir = Path(task_context["project_dir"])
        prompt_content = self.prompt_for(task_context)
        prompt_path = self.write_prompt_file(project_dir, prompt_content)

        cmd = self.executable_argv() + ["chat", "--query-file",
                                        str(prompt_path), "--oneshot", "-Q"]
        options = (self.config.get("agent_options") or {}).get("hermes") or {}
        if options.get("model"):
            cmd += ["-m", options["model"]]
        if options.get("provider"):
            cmd += ["--provider", options["provider"]]

        result = run_command(
            cmd,
            cwd=self.working_dir(task_context),
            timeout=self.config.get("timeout_seconds", 600),
        )
        if not result.success:
            # legacy fallback: query on the command line
            cmd = self.executable_argv() + ["chat", "-q", prompt_content,
                                            "--oneshot"]
            if options.get("model"):
                cmd += ["-m", options["model"]]
            result = run_command(
                cmd,
                cwd=self.working_dir(task_context),
                timeout=self.config.get("timeout_seconds", 600),
            )
        return self.result_dict(result)
