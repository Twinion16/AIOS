from pathlib import Path
import os

def get_project_path(project_name: str, config: dict) -> Path:
    projects_root = Path(config.get("projects_root", "./projects")).resolve()
    return projects_root / project_name
