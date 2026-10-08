"""AIOS orchestrator: classify -> resolve project -> context -> agents -> memory.

Workflows:
  BUILD_LOOP   code change:   builder -> reviewer -> fixer -> reviewer ...
  REVIEW       single review: reviewer writes REVIEW.md
  KNOWLEDGE    research/analysis/planning: notes only, no code changes
  HISTORY      history retrieval + analysis: archive raw sessions, extract
               knowledge into Ideas.md
  HUMAN        stop and hand the task to a human

The proven subprocess chain (Terminal -> aios -> python -> opencode) is
preserved; this module extends it with routing, context and history.
"""
import re
from datetime import datetime
from pathlib import Path

from .agents.hermes import HermesAgent
from .agents.kilo import KiloAgent
from .agents.opencode import OpenCodeAgent
from .agents.registry import AgentRegistry
from .context.engine import ContextEngine
from .context.writer import ensure_project_structure, write_template
from .history import HistoryProviderError, OpenCodeHistoryProvider
from .persistence import ProjectMemory
from .projects import ProjectRegistry
from .reporting import AgentReport, read_report
from .state_machine import TaskState
from .task_types import Workflow, classify_task, describe_task, select_workflow

# workflows that never touch application code
KNOWLEDGE_WORKFLOWS = {Workflow.KNOWLEDGE, Workflow.HISTORY}

_AGENT_CLASSES = {
    "opencode": OpenCodeAgent,
    "hermes": HermesAgent,
    "kilo": KiloAgent,
}


class Orchestrator:
    def __init__(self, config, config_path=None):
        self.config = config
        self.config_path = config_path
        self.registry = AgentRegistry.from_config(config)
        self.projects = ProjectRegistry(config)
        self.engine = ContextEngine(config, self.registry,
                                    self._make_history_provider())
        self.max_iter = config.get("max_iterations", 5)

    # ----------------------------------------------------------------- setup
    def _make_history_provider(self):
        hcfg = self.config.get("history") or {}
        oc = hcfg.get("opencode") or {}
        if not oc.get("enabled", True):
            return None
        try:
            return OpenCodeHistoryProvider(
                self.config, db_path=oc.get("db_path", ""))
        except HistoryProviderError as e:
            print(f"[AIOS] History unavailable: {e}")
            return None

    def _agent(self, spec_name: str):
        cls = _AGENT_CLASSES.get(spec_name)
        if cls is None:
            return None
        return cls(self.config)

    # ------------------------------------------------------------------- run
    def run_task(self, project_name: str, task_text: str) -> str:
        project = self.projects.resolve(project_name)
        memory = ProjectMemory(project)

        task_types = classify_task(task_text)
        workflow = select_workflow(task_types)
        print(f"[AIOS] Classified: {describe_task(task_types, workflow)}")

        self._init_project_files(project, task_text, task_types, workflow)
        self._update_current_state(project, memory, {
            "status": TaskState.PLANNING.value,
            "workflow": workflow.value,
            "task_types": task_types,
            "current_agent": "none",
            "iteration": 0,
            "task": task_text,
        })

        if workflow == Workflow.HUMAN:
            return self._finish(project, memory, TaskState.HUMAN_REVIEW,
                                "Task requires human review by request.")
        if workflow == Workflow.HISTORY:
            return self._run_history(project, memory, task_text, task_types)
        if workflow == Workflow.REVIEW:
            return self._run_single(project, memory, task_text, task_types,
                                    Workflow.REVIEW, TaskState.REVIEWING)
        if workflow == Workflow.KNOWLEDGE:
            return self._run_single(project, memory, task_text, task_types,
                                    Workflow.KNOWLEDGE, TaskState.PLANNING)
        return self._run_build_loop(project, memory, task_text, task_types)

    # ------------------------------------------------------- project files
    def _init_project_files(self, project, task_text, task_types, workflow):
        """Create missing state files. Existing knowledge is NEVER erased —
        only TASK.md is rewritten, because a new task starts a new run."""
        ensure_project_structure(project.state_dir)
        for name in ["PROJECT.md", "CURRENT_STATE.md", "HANDOFF.md",
                     "DECISIONS.md", "TODO.md", "RESEARCH.md"]:
            dest = project.state_dir / name
            if not dest.exists():
                write_template(name, dest, project=project.name)
        types_s = ", ".join(t.value for t in task_types)
        write_template(
            "TASK.md", project.state_dir / "TASK.md",
            task=task_text,
            project=project.name,
            task_types=types_s,
            workflow=workflow.value,
            created=datetime.now().isoformat(timespec="seconds"),
        )

    # --------------------------------------------------------- single-run
    def _run_single(self, project, memory, task_text, task_types,
                    workflow, start_state) -> str:
        # a stale verdict must never masquerade as this run's review
        if workflow == Workflow.REVIEW:
            review_path = project.state_dir / "REVIEW.md"
            if review_path.exists():
                try:
                    review_path.unlink()
                except OSError:
                    pass
        bundle = self.engine.build(task_text, task_types, workflow, project)
        if bundle.agent is None:
            return self._finish(
                project, memory, TaskState.ERROR,
                f"No agent available for capability '{bundle.capability}'.")
        agent = self._agent(bundle.agent.name)
        if agent is None:
            return self._finish(
                project, memory, TaskState.ERROR,
                f"No adapter registered for agent '{bundle.agent.name}'.")

        result, report = self._execute(agent, bundle, project, start_state)
        output_kind = "knowledge" if workflow in KNOWLEDGE_WORKFLOWS \
            else "review"

        if not result["success"] or report.status == "failed":
            self._update_current_state(project, memory, {
                "status": TaskState.FAILED.value, "workflow": workflow.value,
                "task_types": task_types, "current_agent": agent.name,
                "task": task_text, "report": report,
            })
            return self._finish(project, memory, TaskState.FAILED,
                                report.summary or "agent run failed")

        detail = report.summary
        if workflow == Workflow.REVIEW:
            verdict = self._parse_verdict(project.state_dir / "REVIEW.md")
            detail = f"verdict={verdict or 'UNKNOWN'}"
            print(f"[AIOS] Review written: {verdict or 'UNKNOWN'}")
        else:
            print(f"[AIOS] Knowledge notes updated: "
                  f"{', '.join(report.notes_changed) or 'see Runs/'}")

        self._update_current_state(project, memory, {
            "status": TaskState.COMPLETE.value, "workflow": workflow.value,
            "task_types": task_types, "current_agent": "none",
            "task": task_text, "report": report, "output_kind": output_kind,
        })
        self._print_report(report)
        return self._finish(project, memory, TaskState.COMPLETE, detail)

    # ------------------------------------------------------------ history
    def _run_history(self, project, memory, task_text, task_types) -> str:
        workflow = Workflow.HISTORY
        bundle = self.engine.build(task_text, task_types, workflow, project)

        archived = len(bundle.history_contexts)
        print(f"[AIOS] History: {archived} session(s) archived under "
              f"History/OpenCode/")
        # raw archives are part of the persistent memory even if the agent
        # run later fails
        memory.sync_tree("History")

        if bundle.agent is None:
            return self._finish(
                project, memory, TaskState.ERROR,
                f"No history-capable agent configured "
                f"(capability '{bundle.capability}').")
        agent = self._agent(bundle.agent.name)
        if agent is None:
            return self._finish(
                project, memory, TaskState.ERROR,
                f"No adapter for agent '{bundle.agent.name}'.")

        self._update_current_state(project, memory, {
            "status": TaskState.RETRIEVING.value, "workflow": workflow.value,
            "task_types": task_types, "current_agent": agent.name,
            "iteration": 0, "task": task_text,
        })
        result, report = self._execute(agent, bundle, project,
                                       TaskState.RETRIEVING)

        # persist extracted knowledge + archives to the vault mirror
        memory.sync("Ideas.md")
        memory.sync_tree("History")

        if not result["success"] or report.status == "failed":
            self._update_current_state(project, memory, {
                "status": TaskState.FAILED.value, "workflow": workflow.value,
                "task_types": task_types, "current_agent": agent.name,
                "task": task_text, "report": report,
            })
            return self._finish(project, memory, TaskState.FAILED,
                                report.summary or "history agent failed")

        notes = ", ".join(report.notes_changed) or "Ideas.md"
        print(f"[AIOS] Extracted knowledge -> {notes}")
        print(f"[AIOS] Raw history preserved -> History/OpenCode/ "
              f"({archived} session(s))")
        self._update_current_state(project, memory, {
            "status": TaskState.COMPLETE.value, "workflow": workflow.value,
            "task_types": task_types, "current_agent": "none",
            "task": task_text, "report": report, "output_kind": "knowledge",
        })
        self._print_report(report)
        return self._finish(project, memory, TaskState.COMPLETE,
                            report.summary or "history retrieved")

    # -------------------------------------------------------- build loop
    def _run_build_loop(self, project, memory, task_text, task_types) -> str:
        workflow = Workflow.BUILD_LOOP
        state = TaskState.BUILDING
        phase = "build"          # build -> review -> fix -> review ...
        iteration = 0

        while iteration < self.max_iter:
            capability = {"build": "build", "fix": "fix", "review": "review"}[phase]
            preferred = {"build": "builder", "fix": "fixer",
                         "review": "reviewer"}[phase]
            spec = self.registry.resolve(capability, preferred,
                                         allowed=project.enabled_agents or None)
            if spec is None:
                return self._finish(
                    project, memory, TaskState.ERROR,
                    f"No agent with capability '{capability}'.")
            agent = self._agent(spec.name)
            if agent is None:
                return self._finish(
                    project, memory, TaskState.ERROR,
                    f"No adapter for agent '{spec.name}'.")

            # stale verdicts must never satisfy the current review
            review_path = project.state_dir / "REVIEW.md"
            if phase == "review" and review_path.exists():
                try:
                    review_path.unlink()
                except OSError:
                    pass

            start_state = {"build": TaskState.BUILDING,
                           "fix": TaskState.FIXING,
                           "review": TaskState.REVIEWING}[phase]
            self._update_current_state(project, memory, {
                "status": start_state.value, "workflow": workflow.value,
                "task_types": task_types, "current_agent": spec.name,
                "phase": phase, "iteration": iteration, "task": task_text,
            })
            print(f"[AIOS] Agent: {spec.name} | State: {start_state.value} "
                  f"| Phase: {phase}")

            bundle = self.engine.build(task_text, task_types, workflow,
                                       project, phase=phase)
            result, report = self._execute(agent, bundle, project,
                                           start_state, phase=phase)

            if phase in ("build", "fix"):
                if not result["success"] or report.status in ("failed", "blocked"):
                    print(f"[AIOS] {spec.name} failed: "
                          f"{report.summary or result['stderr'][:200]}")
                    return self._finish(project, memory, TaskState.FAILED,
                                        report.summary or "agent run failed")
                phase = "review"
                iteration += 1
                continue

            # phase == review
            verdict = self._parse_verdict(review_path)
            if verdict is None:
                print("[AIOS] Reviewer produced no REVIEW.md verdict")
                return self._finish(
                    project, memory, TaskState.ERROR,
                    "reviewer did not produce a REVIEW.md verdict")
            if verdict == "PASS":
                print("[AIOS] Review: PASS")
                self._update_current_state(project, memory, {
                    "status": TaskState.COMPLETE.value,
                    "workflow": workflow.value, "task_types": task_types,
                    "current_agent": "none", "phase": "done",
                    "iteration": iteration, "task": task_text,
                    "review_verdict": "PASS", "report": report,
                })
                return self._finish(project, memory, TaskState.COMPLETE,
                                    "review PASS")
            if verdict == "NEEDS_HUMAN_REVIEW":
                print("[AIOS] Review: NEEDS_HUMAN_REVIEW")
                return self._finish(project, memory, TaskState.HUMAN_REVIEW,
                                    "reviewer escalated")
            print("[AIOS] Review: FAIL -> fix")
            phase = "fix"
            iteration += 1

        print(f"[AIOS] Max iterations reached ({self.max_iter})")
        return self._finish(project, memory, TaskState.HUMAN_REVIEW,
                            "max iterations reached")

    # ------------------------------------------------------------- helpers
    def _execute(self, agent, bundle, project, start_state, phase=None):
        task_context = {
            "project_dir": str(project.state_dir),
            "cwd": str(project.repository) if project.repository else None,
            "task": bundle.task_text,
            "prompt": bundle.prompt,
            "workflow": bundle.workflow.value,
            "phase": phase,
        }
        result = agent.run(task_context)
        report = read_report(project.state_dir, agent.name, result["success"])
        self._log_run(project.state_dir, agent.name, result, report, phase)
        if not result["success"]:
            err = (result.get("stderr") or "").strip()
            print(f"[AIOS] {agent.name} exit code {result['returncode']}"
                  + (f": {err[:300]}" if err else ""))
        return result, report

    def _update_current_state(self, project, memory, data: dict):
        types = data.get("task_types") or []
        report = data.get("report")
        works = data.get("works")
        incomplete = data.get("incomplete")
        if works is None:
            if data.get("output_kind") == "knowledge" or \
                    data.get("workflow") in ("HISTORY", "KNOWLEDGE"):
                works = "Knowledge task — no application code changed."
                incomplete = "Nothing pending in code; see notes for results."
            else:
                works = "TBD"
                incomplete = "TBD"
        report_lines = ""
        if isinstance(report, AgentReport):
            report_lines = f"""
## Last Agent Report ({report.source})
- status: {report.status}
- summary: {report.summary}
- files_changed: {', '.join(report.files_changed) or 'none'}
- notes_changed: {', '.join(report.notes_changed) or 'none'}
- next: {report.next_recommended_action}
- errors: {', '.join(report.errors) or 'none'}
"""
        content = f"""# CURRENT_STATE

- status: {data.get('status')}
- workflow: {data.get('workflow', 'BUILD_LOOP')}
- task_types: {', '.join(t.value for t in types) or 'UNKNOWN'}
- output_kind: {data.get('output_kind', 'code_change')}
- current_agent: {data.get('current_agent', 'none')}
- next_agent: {data.get('next_agent', 'none')}
- phase: {data.get('phase', '-')}
- iteration: {data.get('iteration', 0)}
- max_iterations: {self.max_iter}
- review_verdict: {data.get('review_verdict', '-')}
- task: {data.get('task', '')}
- last_updated: {datetime.now().isoformat(timespec='seconds')}

## What Currently Works
{works}

## What Is Incomplete
{incomplete}

## Blockers
{data.get('blockers', 'None')}

## Issues
{data.get('issues', 'None')}
{report_lines}"""
        memory.write("CURRENT_STATE.md", content)

    @staticmethod
    def _parse_verdict(review_path: Path):
        if not review_path.exists():
            return None
        text = review_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(
            r"##\s*Final\s+Status\s*\n+\s*(PASS|FAIL|NEEDS_HUMAN_REVIEW)\b",
            text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        up = text.upper()
        if "NEEDS_HUMAN_REVIEW" in up:
            return "NEEDS_HUMAN_REVIEW"
        if re.search(r"\bFAIL\b", up):
            return "FAIL"
        if re.search(r"\bPASS\b", up):
            return "PASS"
        return None

    @staticmethod
    def _print_report(report: AgentReport):
        print(f"[AIOS] Report ({report.source}): status={report.status}")
        if report.summary:
            print(f"[AIOS] Summary: {report.summary}")
        if report.files_changed:
            print(f"[AIOS] Code changed: {', '.join(report.files_changed)}")
        if report.next_recommended_action not in ("", "none"):
            print(f"[AIOS] Next: {report.next_recommended_action}")
        for err in report.errors:
            print(f"[AIOS] Error: {err}")

    def _log_run(self, project_dir, agent_name, result, report, phase=None):
        runs = project_dir / "Runs"
        runs.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        phase_s = f"-{phase}" if phase else ""
        path = runs / f"{ts}-{agent_name}{phase_s}.md"
        stdout = (result.get("stdout") or "")[-8000:]
        stderr = (result.get("stderr") or "")[-4000:]
        content = f"""# Agent Run: {agent_name}{f' ({phase})' if phase else ''}

- Started/Logged: {datetime.now().isoformat(timespec='seconds')}
- Status: {'SUCCESS' if result['success'] else 'FAILURE'}
- Return Code: {result['returncode']}
- Report source: {report.source} | status: {report.status}

## Summary
{report.summary or '(no structured summary)'}

## Files changed
{chr(10).join('- ' + f for f in report.files_changed) or '- none'}

## Notes changed
{chr(10).join('- ' + n for n in report.notes_changed) or '- none'}

## STDOUT (tail)
```text
{stdout}
```

## STDERR (tail)
```text
{stderr}
```
"""
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _finish(project, memory, state: TaskState, note: str) -> str:
        print(f"[AIOS] Final state: {state.value} ({note})")
        return state.value
