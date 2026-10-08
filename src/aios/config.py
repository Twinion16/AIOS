import os
from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "obsidian_vault_path": "",
    # PRIVATE RUNTIME DATA lives outside the source repository by default:
    # every user's projects, history archives, and run logs go under
    # ~/.aios/projects (i.e. %USERPROFILE%\.aios\projects on Windows).
    "projects_root": str(Path.home() / ".aios" / "projects"),
    "max_iterations": 5,
    "default_workflow": "review_loop",
    "timeout_seconds": 600,
    "agent_paths": {
        "opencode": "opencode",
        "kilo": "kilo",
        "hermes": "hermes",
    },
    # Agent registry: name -> role / executable / capabilities.
    # Routing is capability-based: workflow -> capability -> agent.
    "agents": {
        "opencode": {
            "role": "builder",
            "executable": "opencode",
            "capabilities": ["build", "fix", "test", "research", "analysis",
                             "history", "documentation", "planning",
                             "new_project", "review"],
        },
        # Verified 2026-10-08: hermes has $0 Nous credits and kilo is not
        # signed in - both disabled by default so a fresh install works on
        # opencode alone. Set enabled: true once credentials exist.
        "hermes": {
            "role": "reviewer",
            "executable": "hermes",
            "capabilities": ["review", "research", "analysis"],
            "enabled": False,
        },
        "kilo": {
            "role": "fixer",
            "executable": "kilo",
            "capabilities": ["fix", "build", "test"],
            "enabled": False,
        },
    },
    "default_enabled_agents": ["opencode"],
    # Explicit project definitions: name -> repository/obsidian/agents.
    "projects": {},
    # History providers (read-only access to prior agent conversations).
    "history": {
        "opencode": {
            "enabled": True,
            "db_path": "",           # empty = auto (opencode db path)
            "max_sessions": 8,
            "max_chars_per_session": 12000,
        },
    },
    "approval_policy": "human_review_on_uncertain",
    "auto_approve_auto_fixes": True,
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def discover_config_path(explicit=None):
    """--config > $AIOS_CONFIG > ./config/config.yaml > ~/.aios/config.yaml."""
    if explicit:
        return explicit
    env = os.environ.get("AIOS_CONFIG")
    if env:
        return env
    local = os.path.join(os.getcwd(), "config", "config.yaml")
    if os.path.exists(local):
        return local
    user_cfg = Path.home() / ".aios" / "config.yaml"
    if user_cfg.exists():
        return str(user_cfg)
    return None


def load_config(config_path=None):
    # Relative paths in config are anchored to the AIOS package root
    # (src/aios/config.py -> <AIOS>), never to the process CWD - running
    # `aios` from any directory must hit the same runtime data.
    root = Path(__file__).resolve().parents[2]
    path = discover_config_path(config_path)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(DEFAULT_CONFIG, user_config)
        config["_config_path"] = path
        base_dir = os.path.dirname(path)
    else:
        config = _deep_merge(DEFAULT_CONFIG, {})
        config["_config_path"] = path if path else None
        base_dir = str(Path.home() / ".aios")

    # Repository root (for {root} placeholders in config values).
    config["_aios_root"] = str(root)

    # Empty string means "use the default"; never allow a relative path to
    # resolve into the source repository by accident.
    if not config.get("projects_root"):
        config["projects_root"] = DEFAULT_CONFIG["projects_root"]

    for key in ("projects_root", "obsidian_vault_path"):
        value = config.get(key)
        if value and not os.path.isabs(value):
            config[key] = str((root / value).resolve())

    # AIOS-owned project registry (config.yaml itself is never rewritten,
    # so user comments survive `aios project create`). Lives next to the
    # active config file, or in ~/.aios when no config file exists.
    registry_path = os.path.join(base_dir, "projects.yaml")
    config["_projects_registry_path"] = registry_path
    if os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            generated = (yaml.safe_load(f) or {}).get("projects") or {}
        # explicitly written config.yaml projects win over generated ones
        config["projects"] = {**generated, **(config.get("projects") or {})}
    return config
