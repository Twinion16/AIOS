from pathlib import Path
import json
import os
from datetime import datetime

class Vault:
    def __init__(self, vault_path: str = ""):
        self.vault_path = Path(vault_path) if vault_path else None

    def ensure_vault(self):
        if not self.vault_path:
            return False
        self.vault_path.mkdir(parents=True, exist_ok=True)
        return True

    def write_note(self, relative_path: str, content: str):
        if not self.vault_path:
            return False
        full_path = self.vault_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    def read_note(self, relative_path: str):
        if not self.vault_path:
            return None
        full_path = self.vault_path / relative_path
        if not full_path.exists():
            return None
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
