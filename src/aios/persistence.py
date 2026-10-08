"""Obsidian as SHARED MEMORY (not the execution engine).

All knowledge notes are written into the project state directory first;
when a vault is configured the same note is mirrored under
<vault>/Projects/<project>/ so humans can read it in Obsidian.
Raw history and extracted knowledge are separate paths and never merged.
"""
from pathlib import Path
import shutil

from .projects import Project


class ProjectMemory:
    def __init__(self, project: Project):
        self.project = project

    # ------------------------------------------------------------------ write
    def write(self, rel_path: str, content: str) -> Path:
        """Write a note in project state; mirror to vault if configured."""
        target = self.project.state_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._mirror(target, rel_path)
        return target

    def append(self, rel_path: str, content: str) -> Path:
        target = self.project.state_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if content.strip() in existing:
                return target  # idempotent: never duplicate identical notes
            content = existing.rstrip() + "\n\n" + content
        return self.write(rel_path, content)

    def sync(self, rel_path: str) -> bool:
        src = self.project.state_dir / rel_path
        if src.is_file():
            return self._mirror(src, rel_path)
        return False

    def sync_tree(self, rel_dir: str) -> int:
        """Mirror a whole subdirectory (e.g. History/) to the vault."""
        root = self.project.state_dir / rel_dir
        if not root.is_dir():
            return 0
        count = 0
        for f in root.rglob("*"):
            if f.is_file():
                rel = f.relative_to(self.project.state_dir).as_posix()
                if self._mirror(f, rel):
                    count += 1
        return count

    # ------------------------------------------------------------------- read
    def read(self, rel_path: str):
        src = self.project.state_dir / rel_path
        if not src.exists():
            return None
        return src.read_text(encoding="utf-8")

    def exists(self, rel_path: str) -> bool:
        return (self.project.state_dir / rel_path).exists()

    # ----------------------------------------------------------------- mirror
    def _mirror(self, src: Path, rel_path: str) -> bool:
        if not self.project.obsidian:
            return False
        dest = self.project.obsidian / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(src, dest)
            return True
        except OSError:
            return False
