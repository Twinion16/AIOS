import os
import shutil
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

TEMPLATE_FILES = [
    "PROJECT.md",
    "CURRENT_STATE.md",
    "TASK.md",
    "HANDOFF.md",
    "REVIEW.md",
    "DECISIONS.md",
    "TODO.md",
    "RESEARCH.md",
]


def ensure_project_structure(project_dir: Path):
    project_dir.mkdir(parents=True, exist_ok=True)
    for name in ["Agents", "Runs"]:
        (project_dir / name).mkdir(parents=True, exist_ok=True)


def write_template(template_name: str, dest_path: Path, **kwargs):
    ensure_template_exists(template_name)
    template_path = TEMPLATES_DIR / template_name
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    for key, value in kwargs.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_template_exists(template_name: str):
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        # Create minimal fallback if missing
        template_path.parent.mkdir(parents=True, exist_ok=True)
        fallback = f"# {template_name}\n"
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(fallback)
