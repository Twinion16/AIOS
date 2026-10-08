"""Task classification and workflow routing.

Rule-based, deliberately simple. Returns ALL matched intents for a task;
workflow selection is a separate concern (select_workflow).
"""
from enum import Enum
import re


class TaskType(str, Enum):
    NEW_PROJECT = "NEW_PROJECT"
    PLANNING = "PLANNING"
    BUILD = "BUILD"
    FIX = "FIX"
    TEST = "TEST"
    RESEARCH = "RESEARCH"
    REVIEW = "REVIEW"
    ANALYSIS = "ANALYSIS"
    HISTORY_RETRIEVAL = "HISTORY_RETRIEVAL"
    DOCUMENTATION = "DOCUMENTATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class Workflow(str, Enum):
    BUILD_LOOP = "BUILD_LOOP"          # code change: build -> review -> fix loop
    REVIEW = "REVIEW"                  # single review run -> REVIEW.md
    KNOWLEDGE = "KNOWLEDGE"            # research/analysis/planning: notes only
    HISTORY = "HISTORY"                # history retrieval + analysis
    HUMAN = "HUMAN"                    # stop, hand to a human


# Each rule: (TaskType, list of phrases). Matched case-insensitively as
# whole words / phrases. A task may match several types (multi-intent).
_RULES = [
    (TaskType.HISTORY_RETRIEVAL, [
        "previous sessions", "old sessions", "previous conversations",
        "old conversations", "session history", "history", "past conversations",
        "what did we discuss", "we discussed", "previously discussed",
        "earlier discussion", "earlier ideas", "previous opencode",
        "opencode sessions", "past ideas", "earlier sessions",
        "discussed",
    ]),
    (TaskType.FIX, [
        "fix", "debug", "repair", "bug", "broken", "crash", "regression",
        "patch", "does not work", "doesn't work", "not working", "failing",
        "failure", "error when", "exception",
    ]),
    (TaskType.REVIEW, [
        "review", "critique", "code review", "check the implementation",
        "check implementation", "assess", "audit", "review the",
    ]),
    (TaskType.RESEARCH, [
        "research", "find sources", "sources for", "investigate",
        "compare", "comparison", "survey", "look into", "evaluate options",
        "benchmark", "tech scan", "gather information", "find out about",
        "literature", "prior art",
    ]),
    (TaskType.ANALYSIS, [
        "analyze", "analyse", "analysis", "summarize", "summarise",
        "summary", "breakdown", "break down", "rank", "which ones",
        "explain what", "report on", "extract", "categorize", "categorise",
        "tell me which", "worth", "evaluate",
    ]),
    (TaskType.TEST, [
        "write tests", "add tests", "unit test", "test coverage",
        "run the tests", "run tests", "coverage", "tests for",
        "pytest", "integration test", "end to end test",
    ]),
    (TaskType.DOCUMENTATION, [
        "document", "documentation", "docs", "readme", "write a guide",
        "guide for", "changelog", "tutorial", "comment the", "docstring",
        "write docs",
    ]),
    (TaskType.PLANNING, [
        "plan", "planning", "roadmap", "strategy", "next version",
        "backlog", "outline", "design the next", "propose", "proposal",
        "milestone", "sprint",
    ]),
    (TaskType.NEW_PROJECT, [
        "new project", "start a project", "scaffold", "bootstrap",
        "initialize project", "initialise project", "set up a project",
        "create a project", "empty project",
    ]),
    (TaskType.BUILD, [
        "build", "implement", "create", "add a feature", "add feature",
        "develop", "write code", "code this", "integrate", "extend",
        "add support for", "make it", "generate", "refactor", "port to",
        "add android", "new feature", "feature",
    ]),
    (TaskType.HUMAN_REVIEW, [
        "human review", "ask a human", "escalate", "need a human",
        "flag for human",
    ]),
]

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
    "are", "be", "this", "that", "it", "its", "with", "from", "at", "by",
    "as", "we", "our", "my", "me", "you", "your", "please", "can", "could",
    "would", "should", "do", "does", "did", "have", "has", "had", "will",
    "shall", "may", "might", "not", "no", "yes", "if", "then", "than",
    "when", "what", "which", "who", "whom", "how", "why", "where", "all",
    "any", "some", "more", "most", "other", "into", "also", "up", "out",
    "about", "over", "just", "only", "very", "here", "there", "them",
    "they", "these", "those", "am", "was", "were", "been", "being",
    "aios", "task", "project", "agent", "ai",
}


def classify_task(task_text: str):
    """Return all matching TaskTypes, best-scored first."""
    text = (task_text or "").lower()
    scores = {}
    for task_type, phrases in _RULES:
        score = 0
        for phrase in phrases:
            if " " in phrase:
                if phrase in text:
                    score += 2
            else:
                if re.search(r"\b" + re.escape(phrase) + r"\b", text):
                    score += 1
        if score > 0:
            scores[task_type] = score
    if not scores:
        return [TaskType.BUILD]
    return sorted(scores, key=lambda t: (-scores[t], t.value))


# Workflows that only make sense as a single run (no build/review loop).
_SINGLE_RUN_WORKFLOWS = {Workflow.REVIEW, Workflow.KNOWLEDGE, Workflow.HISTORY}

_CODE_WORKFLOW_TYPES = {
    TaskType.BUILD, TaskType.FIX, TaskType.TEST, TaskType.NEW_PROJECT,
    TaskType.DOCUMENTATION,
}

_KNOWLEDGE_TYPES = {TaskType.RESEARCH, TaskType.ANALYSIS, TaskType.PLANNING}


def select_workflow(task_types):
    """Pick the workflow for a (possibly multi-intent) task.

    Priority: HISTORY > REVIEW-only > code-change loop > knowledge > default.
    Default is BUILD_LOOP to preserve the original working behaviour when
    nothing matched.
    """
    types = set(task_types)
    if TaskType.HUMAN_REVIEW in types:
        return Workflow.HUMAN
    if TaskType.HISTORY_RETRIEVAL in types:
        return Workflow.HISTORY
    if TaskType.REVIEW in types and not (types & _CODE_WORKFLOW_TYPES):
        return Workflow.REVIEW
    if types & _CODE_WORKFLOW_TYPES:
        return Workflow.BUILD_LOOP
    if types & _KNOWLEDGE_TYPES:
        return Workflow.KNOWLEDGE
    if TaskType.REVIEW in types:
        return Workflow.REVIEW
    return Workflow.BUILD_LOOP


# Workflow -> capability required from an agent (used by the agent registry).
WORKFLOW_CAPABILITY = {
    Workflow.BUILD_LOOP: "build",
    Workflow.REVIEW: "review",
    Workflow.KNOWLEDGE: "research",
    Workflow.HISTORY: "history",
    Workflow.HUMAN: "human",
}

# Preferred agent role per workflow (best-effort tie-break).
WORKFLOW_PREFERRED_ROLE = {
    Workflow.BUILD_LOOP: "builder",
    Workflow.REVIEW: "reviewer",
    Workflow.KNOWLEDGE: "researcher",
    Workflow.HISTORY: "researcher",
    Workflow.HUMAN: None,
}


def describe_task(task_types, workflow):
    parts = ", ".join(t.value for t in task_types)
    return f"types=[{parts}] workflow={workflow.value}"
