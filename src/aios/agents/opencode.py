from .base import BaseAgent
from ..execution.process import run_command


class OpenCodeAgent(BaseAgent):
    def __init__(self, config):
        super().__init__("opencode", config)

    def legacy_prompt(self, task_context) -> str:
        task = task_context.get("task", "unknown")
        return f"""You are the BUILD agent for AIOS.

Read project context first. Understand current state before changing anything.

CURRENT TASK:
{task}

REQUIREMENTS:
1. Read PROJECT.md, CURRENT_STATE.md, TASK.md, HANDOFF.md if they exist
2. Inspect the actual codebase
3. Implement the requested work
4. Run relevant tests if they exist
5. Update CURRENT_STATE.md, HANDOFF.md, DECISIONS.md, TODO.md as needed
6. HANDOFF status must be READY_FOR_REVIEW when complete.
"""

    def run(self, task_context):
        project_dir = task_context["project_dir"]
        prompt_content = self.prompt_for(task_context)
        self.write_prompt_file(project_dir, prompt_content)

        cmd = self.executable_argv() + ["run", prompt_content]
        result = run_command(
            cmd,
            cwd=self.working_dir(task_context),
            timeout=self.config.get("timeout_seconds", 600),
        )
        return self.result_dict(result)
