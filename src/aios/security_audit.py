"""Security & privacy audit: is this repository safe to publish?

Inspects the working tree, the Git index, and Git history for private data,
secrets, and personal filesystem paths before any public release.

Rules of engagement:
- Never prints secret values - only file, line number, and pattern name.
- Never modifies anything (read-only audit).
- Verdicts: PASS (0 findings) / WARNINGS (non-blocking) / FAIL (blocking).
"""
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

# ------------------------------------------------------------------ patterns
# Strong: high-confidence credential material. Finding = FAIL.
STRONG_PATTERNS = [
    ("private_key_block", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.")),
]

# Weak: assignment-shaped strings that *may* be secrets. Finding = WARN.
WEAK_PATTERNS = [
    ("credential_assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|passwd|password|client_secret)"
        r"\s*[:=]\s*[\"'][^\"']{8,}[\"']")),
]

# Personal filesystem identity. Finding = FAIL in tracked files.
PERSONAL_PATH_PATTERNS = [
    ("windows_user_path", re.compile(
        r"(?i)[a-z]:[\\/]+Users[\\/]+"
        r"(?![<%]|USERNAME\b|path\b|your-)[^\\/\s\"'`]+")),
    ("unix_home_path", re.compile(
        r"/home/(?![<]|user\b|example\b)[A-Za-z0-9._-]+")),
]

ALL_CONTENT_PATTERNS = [
    (name, rx, "strong") for name, rx in STRONG_PATTERNS
] + [
    (name, rx, "weak") for name, rx in WEAK_PATTERNS
] + [
    (name, rx, "personal") for name, rx in PERSONAL_PATH_PATTERNS
]

# Tracked paths that must never appear in the index (FAIL).
TRACKED_DENY = [
    (re.compile(r"^projects/"), "private runtime project data"),
    (re.compile(r"[/\\]Runs[/\\]"), "agent run logs"),
    (re.compile(r"[/\\]History[/\\]"), "agent conversation history"),
    (re.compile(r"__pycache__|\.pyc$"),
     "compiled bytecode (embeds local paths)"),
    (re.compile(r"egg-info"), "packaging metadata (machine-local)"),
    (re.compile(r"^config/config\.yaml$"), "local configuration"),
    (re.compile(r"(^|/)projects\.yaml$"), "local project registry"),
    (re.compile(r"(^|/)\.env"), "environment secret file"),
    (re.compile(r"auth\.json$|credentials\.json$"), "credential store"),
    (re.compile(r"\.(db|sqlite3?)$"), "database"),
    (re.compile(r"\.(pem|key|p12|pfx)$"), "key material"),
    (re.compile(r"(^|/)\.netrc$|(^|/)\.pypirc$"), "credential file"),
]

# Paths that must never appear in ANY commit's history (FAIL).
HISTORY_DENY = TRACKED_DENY + [
    (re.compile(r"\.pytest_cache"), "test cache"),
]

TEXT_EXT = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml",
            ".cfg", ".ini", ".csv", ".html", ".css", ".js", ".sh", ".ps1"}


@dataclass
class AuditReport:
    root: Path
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ok: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.failures:
            return "FAIL"
        if self.warnings:
            return "WARNINGS"
        return "PASS"

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0


def _git(root: Path, *args: str, ok_codes=(0, 1)) -> Optional[str]:
    """Run a git command; None when git or the repo is unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode not in ok_codes:
        return None
    return out.stdout


def _is_text_name(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_EXT or Path(name).name == ".gitignore"


def _scan_text(text: str) -> List[Tuple[str, int, str]]:
    """Return (pattern_name, line_no, severity) hits.

    Never includes the matched text itself - line numbers and pattern
    names only, so no secret can leak into audit output or logs.
    """
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx, severity in ALL_CONTENT_PATTERNS:
            m = rx.search(line)
            if m and not (severity == "personal" and "<" in m.group(0)):
                hits.append((name, lineno, severity))
    return hits


def _iter_commit_texts(repo: Path, rev: str) -> Iterator[Tuple[str, str]]:
    """Yield (path, text) for every text file in one commit.

    Sequential `git show` reads - avoids pipe deadlocks that a
    `cat-file --batch` stdin/stdout interleave can cause.
    """
    names_out = _git(repo, "ls-tree", "-r", "--name-only", rev)
    if not names_out:
        return
    names = [n for n in names_out.splitlines() if n and _is_text_name(n)]
    for name in names:
        data = _git(repo, "show", f"{rev}:{name}")
        if data is not None:
            yield name, data


# ------------------------------------------------------------------- checks
def check_gitignore(repo: Path, report: AuditReport):
    gi = repo / ".gitignore"
    if not gi.exists():
        report.failures.append(".gitignore is missing")
        return
    required = ["projects/demo/Runs/x.md", "config/config.yaml",
                "config/projects.yaml", "src/aios/__pycache__/m.pyc",
                "run.db", ".env", "auth.json"]
    if _git(repo, "rev-parse", "--is-inside-work-tree") is None:
        text = gi.read_text(encoding="utf-8", errors="replace")
        missing = [p for p in required
                   if p.split("/")[0].rstrip("/") not in text
                   and Path(p).name not in text]
        if missing:
            report.warnings.append(
                ".gitignore does not obviously cover: " + ", ".join(missing))
        else:
            report.ok.append(".gitignore covers private-data patterns")
        return
    missing = []
    for probe in required:
        r = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", probe],
            timeout=10)
        if r.returncode != 0:
            missing.append(probe)
    if missing:
        report.warnings.append(
            ".gitignore does not protect: " + ", ".join(missing))
    else:
        report.ok.append(".gitignore protects all private-data patterns "
                         "(verified with git check-ignore)")


def _cap(items: List[str], limit: int = 10) -> List[str]:
    if len(items) <= limit:
        return items
    head = items[:limit]
    head.append(f"... +{len(items) - limit} more (same category)")
    return head


def check_index(repo: Path, report: AuditReport):
    out = _git(repo, "ls-files")
    if out is None:
        report.skipped.append("git index scan (not a git repository)")
        return
    files = [f for f in out.splitlines() if f]
    denied = []
    for f in files:
        for rx, why in TRACKED_DENY:
            if rx.search(f):
                denied.append(f"{f} ({why})")
                break
    if denied:
        for d in _cap(denied):
            report.failures.append(f"tracked private/generated file: {d}")
    else:
        report.ok.append(f"index clean: {len(files)} tracked files, "
                         "no private/generated data")

    # content scan over everything that WOULD be committed:
    # tracked files + untracked (non-ignored) files
    scan_out = _git(repo, "ls-files", "-c", "-o", "--exclude-standard")
    scan_files = [f for f in (scan_out or "").splitlines() if f]
    strong, personal, weak = [], [], []
    for f in scan_files:
        p = repo / f
        if not p.is_file() or not _is_text_name(f):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, lineno, severity in _scan_text(text):
            msg = f"{f}:{lineno} matches {name}"
            if severity == "strong":
                strong.append(msg)
            elif severity == "personal":
                personal.append(msg)
            else:
                weak.append(msg)
    for msg in _cap(strong):
        report.failures.append("secret pattern: " + msg)
    for msg in _cap(personal):
        report.failures.append("personal path: " + msg)
    for msg in _cap(weak):
        report.warnings.append("possible secret: " + msg)
    if scan_files and not (strong or personal or weak):
        report.ok.append(
            f"content scan of {len(scan_files)} to-be-committed files: "
            "no secrets, no personal paths")


def check_history(repo: Path, report: AuditReport):
    out = _git(repo, "log", "--all", "--name-only", "--format=%H")
    if out is None:
        report.skipped.append("git history scan (not a git repository)")
        return
    commits = set()
    paths = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"[0-9a-f]{7,40}", line):
            commits.add(line)
        else:
            paths.add(line)
    if not commits:
        report.ok.append("git history: empty")
        return

    exposed = []
    for f in sorted(paths):
        for rx, why in HISTORY_DENY:
            if rx.search(f):
                exposed.append(f"{f} ({why})")
                break
    if exposed:
        preview = exposed[:5]
        more = f" (+{len(exposed) - 5} more)" if len(exposed) > 5 else ""
        report.failures.append(
            "history exposure: private/generated paths in "
            f"{len(commits)} commit(s): " + "; ".join(preview) + more +
            " -> history rewrite required before publishing")
    else:
        report.ok.append(f"git history: {len(commits)} commit(s), "
                         f"{len(paths)} paths, no private/generated data")

    # secret/personal content inside historical versions of text files
    seen = set()
    hist_strong, hist_personal, hist_weak = [], [], []
    for rev in sorted(commits):
        for fname, text in _iter_commit_texts(repo, rev):
            if (fname, text) in seen:
                continue
            seen.add((fname, text))
            for name, lineno, severity in _scan_text(text):
                msg = f"history {rev[:8]}:{fname}:{lineno} matches {name}"
                if severity == "strong":
                    hist_strong.append(msg)
                elif severity == "personal":
                    hist_personal.append(msg)
                else:
                    hist_weak.append(msg)
    for msg in _cap(hist_strong):
        report.failures.append("secret pattern in history: " + msg)
    for msg in _cap(hist_personal):
        report.failures.append("personal path in history: " + msg)
    for msg in _cap(hist_weak):
        report.warnings.append("possible secret in history: " + msg)


def check_remotes(repo: Path, report: AuditReport):
    out = _git(repo, "remote")
    if out is None:
        return
    remotes = [r.strip() for r in out.splitlines() if r.strip()]
    if remotes:
        report.ok.append(
            "git remotes: " + ", ".join(remotes) + " (informational; pushing "
            "requires explicit human approval per docs/PUBLIC_RELEASE_CHECKLIST.md)")
    else:
        report.ok.append("no git remotes configured (nothing was ever pushed)")


def check_large_files(repo: Path, report: AuditReport):
    out = _git(repo, "ls-files", "-z")
    if not out:
        return
    big = []
    for f in out.split("\0"):
        if not f:
            continue
        p = repo / f
        try:
            if p.is_file() and p.stat().st_size > 1_000_000:
                big.append(f"{f} ({p.stat().st_size // 1_000_000} MB)")
        except OSError:
            continue
    if big:
        report.warnings.append("large tracked files: " + ", ".join(big))
    else:
        report.ok.append("no tracked files > 1 MB")


# -------------------------------------------------------------------- entry
def run_audit(root=None) -> AuditReport:
    repo = Path(root) if root else Path.cwd()
    report = AuditReport(root=repo)
    check_gitignore(repo, report)
    check_index(repo, report)
    check_history(repo, report)
    check_remotes(repo, report)
    check_large_files(repo, report)
    return report
