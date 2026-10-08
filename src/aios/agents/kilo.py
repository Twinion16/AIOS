from pathlib import Path
from .base import BaseAgent
from ..execution.process import run_command


class KiloAgent(BaseAgent):
    def __init__(self, config):
        super().__init__("kilo", config)

    def legacy_prompt(self, task_context) -> str:
        project_dir = Path(task_context["project_dir"])
        review_path = project_dir / "REVIEW.md"
        review_content = (review_path.read_text(encoding="utf-8")
                          if review_path.exists() else "No review found")
        return f"""You are the FIX agent for AIOS.

Read TASK.md, CURRENT_STATE.md, HANDOFF.md, REVIEW.md, DECISIONS.md.
Reproduce and fix the reported issues. Use engineering judgment.
Run relevant tests. Update CURRENT_STATE.md and HANDOFF.md.
HANDOFF must be READY_FOR_REVIEW when done.

REVIEW CONTENT:
{review_content}
"""

    def run(self, task_context):
        project_dir = Path(task_context["project_dir"])
        prompt_content = self.prompt_for(task_context)
        self.write_prompt_file(project_dir, prompt_content)

        cmd = self.executable_argv() + ["run", prompt_content]
        result = run_command(
            cmd,
            cwd=self.working_dir(task_context),
            timeout=self.config.get("timeout_seconds", 600),
        )
        return self.result_dict(result)
