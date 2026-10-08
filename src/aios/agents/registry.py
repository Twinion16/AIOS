"""Agent registry: name, role, executable, capabilities, prompt templates.

Routing rule: task workflow -> required capability -> agent that has it
(preferred role breaks ties). Never hard-code "always OpenCode".
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# workflow value -> prompt template file (per agent, with fallbacks)
_DEFAULT_PROMPTS = {
    "BUILD_LOOP": {
        "builder": "opencode_build.md",
        "fixer": "kilo_fix.md",
        "reviewer": "hermes_review.md",
    },
    "REVIEW": {"reviewer": "hermes_review.md",
               "builder": "hermes_review.md",
               "fixer": "hermes_review.md"},
    "KNOWLEDGE": {"researcher": "opencode_research.md",
                  "builder": "opencode_analysis.md"},
    "HISTORY": {"researcher": "opencode_history.md",
                "builder": "opencode_history.md"},
}

# Inside the build loop the PHASE decides the prompt, not the agent name —
# any agent that reviews gets the review template, whoever ends up fixing
# gets the fix template.
_PHASE_PROMPTS = {
    "build": "opencode_build.md",
    "review": "hermes_review.md",
    "fix": "kilo_fix.md",
}


@dataclass
class AgentSpec:
    name: str
    role: str
    executable: str
    capabilities: set = field(default_factory=set)
    prompt_template: str = ""
    enabled: bool = True

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def prompt_for(self, workflow: str, phase: str = None) -> Path:
        if phase and phase in _PHASE_PROMPTS:
            return PROMPTS_DIR / _PHASE_PROMPTS[phase]
        if self.prompt_template:
            return PROMPTS_DIR / self.prompt_template
        fallback = _DEFAULT_PROMPTS.get(workflow, {}).get(self.role)
        if fallback:
            return PROMPTS_DIR / fallback
        # generic fallbacks by capability naming convention
        guess = PROMPTS_DIR / f"{self.name}.md"
        return guess if guess.exists() else PROMPTS_DIR / "opencode_build.md"


DEFAULT_AGENTS = {
    "opencode": AgentSpec(
        name="opencode",
        role="builder",
        executable="opencode",
        capabilities={"build", "fix", "test", "research", "analysis",
                      "history", "documentation", "planning", "new_project"},
    ),
    "hermes": AgentSpec(
        name="hermes",
        role="reviewer",
        executable="hermes",
        capabilities={"review", "research", "analysis"},
    ),
    "kilo": AgentSpec(
        name="kilo",
        role="fixer",
        executable="kilo",
        capabilities={"fix", "build", "test"},
    ),
}

# role precedence when several agents share a capability for a workflow
_ROLE_PRECEDENCE = {
    "build": ["builder", "fixer", "researcher", "reviewer"],
    "fix": ["fixer", "builder", "reviewer"],
    "test": ["builder", "fixer", "researcher"],
    "review": ["reviewer", "builder"],
    "research": ["researcher", "builder", "reviewer"],
    "analysis": ["researcher", "builder", "reviewer"],
    "history": ["researcher", "builder"],
    "documentation": ["builder", "researcher"],
    "planning": ["researcher", "builder"],
    "new_project": ["builder"],
}


class AgentRegistry:
    def __init__(self, agents: Dict[str, AgentSpec]):
        self._agents = agents

    @classmethod
    def from_config(cls, config: dict) -> "AgentRegistry":
        """Build from config `agents:` section, merged over defaults."""
        agents = {n: AgentSpec(**{**vars(spec)}) for n, spec in DEFAULT_AGENTS.items()}
        for name, overrides in (config.get("agents") or {}).items():
            base = agents.get(name) or AgentSpec(name=name, role="", executable=name)
            if "role" in overrides:
                base.role = overrides["role"]
            if "executable" in overrides:
                base.executable = overrides["executable"]
            if "capabilities" in overrides:
                base.capabilities = set(overrides["capabilities"])
            if "prompt_template" in overrides:
                base.prompt_template = overrides["prompt_template"]
            if "enabled" in overrides:
                base.enabled = bool(overrides["enabled"])
            agents[name] = base
        return cls(agents)

    def get(self, name: str) -> AgentSpec:
        if name not in self._agents:
            raise KeyError(f"Unknown agent: {name}")
        return self._agents[name]

    def all(self) -> List[AgentSpec]:
        return [a for a in self._agents.values() if a.enabled]

    def candidates(self, capability: str,
                   allowed=None) -> List[AgentSpec]:
        """Enabled agents with `capability`, best role first.

        `allowed` optionally restricts to a project's enabled_agents list.
        """
        capable = [a for a in self.all() if a.has(capability)]
        if allowed:
            allowed = set(allowed)
            capable = [a for a in capable if a.name in allowed]
        precedence = _ROLE_PRECEDENCE.get(capability, [])
        return sorted(
            capable,
            key=lambda a: (precedence.index(a.role)
                           if a.role in precedence else len(precedence),
                           a.name),
        )

    def resolve(self, capability: str,
                preferred_role: Optional[str] = None,
                allowed=None) -> Optional[AgentSpec]:
        cands = self.candidates(capability, allowed=allowed)
        if not cands:
            return None
        if preferred_role:
            for c in cands:
                if c.role == preferred_role:
                    return c
        return cands[0]
