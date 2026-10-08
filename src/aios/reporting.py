"""Structured agent output contract.

Every AIOS agent is instructed to write AIOS_REPORT.json in the project
directory. AIOS reads it after the run; if it is missing or malformed, a
conservative default derived from the exit code is used — prose is never the
only signal, but a missing report never crashes the orchestrator either.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

REPORT_FILENAME = "AIOS_REPORT.json"

# Appended to every prompt so agents know the contract.
CONTRACT_TEXT = f"""
## OUTPUT CONTRACT (required)

When finished, write `{REPORT_FILENAME}` into the project directory as JSON
(UTF-8, no comments) with exactly these keys:

{{
  "status": "completed" | "failed" | "blocked",
  "summary": "<one or two sentences>",
  "files_changed": ["relative/path.py", ...],
  "notes_changed": ["CURRENT_STATE.md", "History/OpenCode/....md", ...],
  "next_recommended_action": "<what a human or next agent should do, or \\"none\\">",
  "errors": ["<problem>", ...]
}}

Rules:
- Report ONLY what you actually did. Empty lists are fine.
- `notes_changed` includes every .md note you wrote or updated.
- If you could not finish, set status to "failed" or "blocked" and explain
  in `errors`. Never claim success you did not verify.
"""


@dataclass
class AgentReport:
    status: str = "unknown"
    summary: str = ""
    files_changed: List[str] = field(default_factory=list)
    notes_changed: List[str] = field(default_factory=list)
    next_recommended_action: str = "none"
    errors: List[str] = field(default_factory=list)
    source: str = "default"      # "report" | "default" | "exit-code"
    raw: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "completed"


def read_report(project_dir: Path, agent_name: str,
                exit_success: bool) -> AgentReport:
    """Read AIOS_REPORT.json if present; otherwise derive from exit code.

    The report is rotated into Runs/ after reading so the next agent starts
    clean and cannot inherit a stale success claim.
    """
    path = project_dir / REPORT_FILENAME
    report = None
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                report = AgentReport(
                    status=str(data.get("status", "unknown")),
                    summary=str(data.get("summary", "")),
                    files_changed=_strlist(data.get("files_changed")),
                    notes_changed=_strlist(data.get("notes_changed")),
                    next_recommended_action=str(
                        data.get("next_recommended_action") or "none"),
                    errors=_strlist(data.get("errors")),
                    source="report",
                    raw=data,
                )
        except (ValueError, OSError):
            report = None
        try:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            runs = project_dir / "Runs"
            runs.mkdir(exist_ok=True)
            path.rename(runs / f"{ts}-{agent_name}-report.json")
        except OSError:
            try:
                path.unlink()
            except OSError:
                pass

    if report is None:
        report = AgentReport(
            status="completed" if exit_success else "failed",
            summary="Agent produced no structured report; status derived "
                    "from exit code only.",
            errors=[] if exit_success else ["agent exited with non-zero code"],
            source="exit-code",
        )
    return report


def _strlist(value) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []
