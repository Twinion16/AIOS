"""Explicit project selection and resolution.

A project = repository (code) + Obsidian memory + task state + agent history.
Nothing is silently mixed: every task runs against a named project whose
state lives in its own directory.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


class UnknownProjectError(Exception):
    pass


@dataclass
class Project:
    name: str
    state_dir: Path                 # AIOS task state (PROJECT/TASK/CURRENT_STATE...)
    repository: Optional[Path] = None       # where the application code lives
    obsidian: Optional[Path] = None         # vault folder for this project
    enabled_agents: List[str] = field(default_factory=list)

    @property
    def history_dir(self) -> Path:
        return self.state_dir / "History"

    @property
    def runs_dir(self) -> Path:
        return self.state_dir / "Runs"

    @property
    def ideas_path(self) -> Path:
        return self.state_dir / "Ideas.md"


class ProjectRegistry:
    def __init__(self, config: dict):
        self.config = config
        self.projects_root = Path(config["projects_root"])
        self._defs = dict(config.get("projects") or {})
        self._default_agents = list(
            config.get("default_enabled_agents")
            or ["opencode", "hermes", "kilo"]
        )
        # AIOS-owned registry file; the user's config.yaml is never rewritten.
        self.registry_path = config.get("_projects_registry_path")

    def list(self) -> List[str]:
        names = set(self._defs)
        if self.projects_root.exists():
            names.update(p.name for p in self.projects_root.iterdir()
                         if p.is_dir())
        if not names:
            names.add("default")
        return sorted(names)

    def exists(self, name: str) -> bool:
        return name in self._defs or (self.projects_root / name).exists()

    def resolve(self, name: str) -> Project:
        if not self.exists(name):
            raise UnknownProjectError(
                f"Unknown project '{name}'. Known: {', '.join(self.list())}. "
                f"Create it with: aios project create {name}"
            )
        d = self._defs.get(name) or {}
        state_dir = self.projects_root / name

        repository = None
        if d.get("repository"):
            repository = Path(d["repository"])
        elif (state_dir / ".git").exists():
            repository = state_dir

        obsidian = None
        if d.get("obsidian"):
            obsidian = Path(d["obsidian"])
        elif self.config.get("obsidian_vault_path"):
            obsidian = (Path(self.config["obsidian_vault_path"])
                        / "Projects" / name)

        return Project(
            name=name,
            state_dir=state_dir,
            repository=repository,
            obsidian=obsidian,
            enabled_agents=list(d.get("enabled_agents") or self._default_agents),
        )

    def create(self, name: str, repository: str = "",
               obsidian: str = "", enabled_agents=None) -> Project:
        """Register a project in config `projects:` and create its state dir."""
        entry = {
            "repository": repository,
            "obsidian": obsidian,
            "enabled_agents": enabled_agents or self._default_agents,
        }
        self._defs[name] = entry
        project = self.resolve(name)
        project.state_dir.mkdir(parents=True, exist_ok=True)
        return project

    def save_definitions(self, config_path: Optional[str] = None) -> bool:
        """Persist project definitions to the AIOS-owned projects.yaml.

        `config_path` is accepted for backward compatibility but ignored:
        the user's config file (with its comments) is never rewritten.
        """
        import yaml
        target = self.registry_path
        if not target:
            return False
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data["projects"] = self._defs
        header = (
            "# AIOS project registry (generated).\n"
            "# Edit freely; user config.yaml entries with the same name win.\n"
        )
        body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        path.write_text(header + body, encoding="utf-8")
        return True
