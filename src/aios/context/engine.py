"""ContextEngine: task -> relevant context -> prompt bundle.

Never passes the entire vault to an agent; each workflow gets exactly the
state files (and, for HISTORY, the archived sessions) that matter.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ..agents.registry import AgentRegistry, AgentSpec
from ..history.base import HistoryProvider, SessionContext
from ..persistence import ProjectMemory
from ..projects import Project
from ..task_types import (
    WORKFLOW_CAPABILITY,
    WORKFLOW_PREFERRED_ROLE,
    Workflow,
)

# workflow -> state files that matter (relative; included only if they exist)
WORKFLOW_FILES = {
    Workflow.BUILD_LOOP: [
        "PROJECT.md", "TASK.md", "CURRENT_STATE.md", "HANDOFF.md",
        "DECISIONS.md", "TODO.md",
    ],
    Workflow.REVIEW: [
        "PROJECT.md", "TASK.md", "CURRENT_STATE.md", "HANDOFF.md",
        "REVIEW.md", "DECISIONS.md",
    ],
    Workflow.KNOWLEDGE: [
        "PROJECT.md", "TASK.md", "CURRENT_STATE.md", "RESEARCH.md",
        "DECISIONS.md",
    ],
    Workflow.HISTORY: [
        "PROJECT.md", "TASK.md", "DECISIONS.md", "Ideas.md",
    ],
    Workflow.HUMAN: ["TASK.md", "CURRENT_STATE.md"],
}


@dataclass
class ContextBundle:
    task_text: str
    task_types: list
    workflow: Workflow
    capability: str
    project: Project
    agent: Optional[AgentSpec]
    context_files: List[str] = field(default_factory=list)
    context_summary: str = ""
    history_contexts: List[SessionContext] = field(default_factory=list)
    history_manifest: str = ""
    phase: Optional[str] = None
    prompt: str = ""


class ContextEngine:
    def __init__(self, config: dict, registry: AgentRegistry,
                 history_provider: Optional[HistoryProvider] = None):
        self.config = config
        self.registry = registry
        self.history = history_provider

    # ------------------------------------------------------------------ build
    def build(self, task_text: str, task_types: list, workflow: Workflow,
              project: Project, phase: str = None) -> ContextBundle:
        capability = WORKFLOW_CAPABILITY.get(workflow, "build")
        agent = self.registry.resolve(
            capability,
            WORKFLOW_PREFERRED_ROLE.get(workflow),
            allowed=project.enabled_agents or None,
        )
        memory = ProjectMemory(project)

        bundle = ContextBundle(
            task_text=task_text,
            task_types=task_types,
            workflow=workflow,
            capability=capability,
            project=project,
            agent=agent,
            phase=phase,
        )

        # 1. select state files relevant to this workflow
        rel_files = []
        for rel in WORKFLOW_FILES.get(workflow, []):
            if memory.exists(rel):
                rel_files.append(rel)
        bundle.context_files = [
            str((project.state_dir / rel).resolve()) for rel in rel_files
        ]

        # 2. history: retrieve, archive raw sessions, build manifest
        if workflow == Workflow.HISTORY:
            self._add_history(bundle)

        # 3. summary
        repo = str(project.repository) if project.repository else str(
            project.state_dir)
        lines = [
            f"Project: {project.name} (workflow {workflow.value})",
            f"Codebase directory: {repo}",
            f"State files included: {len(bundle.context_files)} "
            f"of {len(WORKFLOW_FILES.get(workflow, []))} possible.",
        ]
        if workflow == Workflow.HISTORY:
            lines.append(
                f"Historical sessions archived: {len(bundle.history_contexts)} "
                f"(raw transcripts under History/OpenCode/)."
            )
        else:
            lines.append("No conversation history included for this workflow.")
        bundle.context_summary = "\n".join(lines)

        # 4. render prompt
        bundle.prompt = self._render(bundle)
        return bundle

    # ----------------------------------------------------------------- history
    def _add_history(self, bundle: ContextBundle):
        contexts: List[SessionContext] = []
        manifest_entries = []
        hcfg = self.config.get("history", {}).get("opencode", {}) \
            if isinstance(self.config.get("history"), dict) else {}
        max_sessions = int(hcfg.get("max_sessions", 8))
        max_chars = int(hcfg.get("max_chars_per_session", 12000))

        if self.history:
            contexts = self.history.extract_relevant_context(
                bundle.task_text,
                max_sessions=max_sessions,
                max_chars_per_session=max_chars,
            )
        else:
            manifest_entries.append(
                "- No history provider configured for this project."
            )

        for ctx in contexts:
            rel = f"History/OpenCode/{ctx.session.id}.md"
            ProjectMemory(bundle.project).write(rel, self._archive(ctx))
            bundle.context_files.append(
                str((bundle.project.state_dir / rel).resolve())
            )
            snippet = ctx.hits[0].text[:200].replace("\n", " ") \
                if ctx.hits else ""
            manifest_entries.append(
                f"- session: {ctx.session.id}\n"
                f"  title: {ctx.session.title or 'UNKNOWN'}\n"
                f"  date: {ctx.session.date_iso}\n"
                f"  score: {ctx.total_score} | matched: "
                f"{', '.join(ctx.matched_terms) or 'NONE'}\n"
                f"  archive: {rel}\n"
                + (f"  snippet: \"{snippet}...\"\n" if snippet else "")
            )

        if contexts:
            manifest_entries.insert(
                0, f"Matched sessions ({len(contexts)}), best first:\n"
            )
        elif self.history:
            # no keyword matches: at least point the agent at real sessions
            recent = self.history.list_sessions(limit=10)
            manifest_entries.append(
                "- No sessions matched the query keywords. Recent sessions "
                "for manual inspection (use `opencode export <id>` if one "
                "looks relevant):\n"
                + "\n".join(
                    f"    - {s.id} | {s.title or 'untitled'} | {s.date_iso}"
                    for s in recent
                )
            )

        bundle.history_contexts = contexts
        bundle.history_manifest = "\n".join(manifest_entries) or "- NONE"

    @staticmethod
    def _archive(ctx: SessionContext) -> str:
        s = ctx.session
        return (
            f"# Archived OpenCode Session: {s.id}\n\n"
            f"- Session ID: {s.id}\n"
            f"- Title: {s.title or 'UNKNOWN'}\n"
            f"- Slug: {s.slug or 'UNKNOWN'}\n"
            f"- Directory: {s.directory or 'UNKNOWN'}\n"
            f"- Date: {s.date_iso}\n"
            f"- Recorded opencode version: {s.version or 'UNKNOWN'}\n"
            f"- Exported by AIOS (read-only) on: "
            f"{datetime.now().isoformat(timespec='seconds')}\n"
            f"- Transcript truncated: {'yes' if ctx.truncated else 'no'}\n"
            f"- Matched terms: {', '.join(ctx.matched_terms) or 'NONE'}\n\n"
            f"## Transcript (raw history — evidence, not conclusions)\n\n"
            f"{ctx.transcript or '(no text parts)'}\n"
        )

    # ----------------------------------------------------------------- render
    def _render(self, bundle: ContextBundle) -> str:
        if not bundle.agent:
            return (
                f"# UNROUTED TASK\n\nNo agent with capability "
                f"'{bundle.capability}' is configured.\n\n"
                f"TASK:\n{bundle.task_text}\n"
            )
        path = bundle.agent.prompt_for(bundle.workflow.value, bundle.phase)
        if path.exists():
            template = path.read_text(encoding="utf-8")
        else:
            template = "# TASK\n{task}\n"
        files_block = (
            "\n".join(f"- {f}" for f in bundle.context_files)
            if bundle.context_files else "- (none — start fresh)"
        )
        replacements = {
            "task": bundle.task_text,
            "project_dir": str(bundle.project.state_dir),
            "context_files": files_block,
            "context_summary": bundle.context_summary,
            "history_manifest": bundle.history_manifest,
        }
        for key, value in replacements.items():
            template = template.replace("{" + key + "}", value)
        return template
