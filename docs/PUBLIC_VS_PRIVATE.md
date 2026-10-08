# PUBLIC vs PRIVATE — release boundary for AIOS

This document defines exactly what may enter a public GitHub repository
and what must stay on this machine. Enforced by `.gitignore`, the
`~/.aios` runtime-data boundary, and `aios security-audit`.

## Principle

The repository ships **the program only**. Everything the program
*produces* on a user's machine — state, logs, conversations, credentials,
local configuration — is private by construction, not by convention.

## PUBLIC — belongs in the repository

| Category | Examples |
|----------|----------|
| Source code | `src/aios/**/*.py` |
| Prompt templates | `src/aios/prompts/*.md` |
| Project templates | `templates/*.md`, `src/templates/*.md` |
| Tests | `tests/*.py`, `tests/*.yaml` (paths via `{root}` placeholder) |
| Configuration **template** | `config/config.example.yaml` (placeholders only) |
| Docs | `README.md`, `docs/*.md` (sanitized — see below) |
| Packaging / housekeeping | `pyproject.toml`, `.gitignore`, `LICENSE` (pending) |

Docs are public only if they contain **no**: real usernames, real
absolute user paths, credential names/values, private conversation text,
or machine-identifying fingerprints. Environment-specific paths appear
only as placeholders (`%USERPROFILE%`, `<USERNAME>`, `path\to\...`).

## PRIVATE — must never be committed

| Category | Location | Why |
|----------|----------|-----|
| Project state | `~/.aios/projects/<name>/*.md` | task state, decisions, handoffs |
| Run logs | `~/.aios/projects/<name>/Runs/` | agent stdout/stderr transcripts |
| Agent prompts sent | `~/.aios/projects/<name>/*_prompt.txt` | task text + context |
| History archives | `~/.aios/projects/<name>/History/` | exported OpenCode conversations |
| Local config | `config/config.yaml`, `config/projects.yaml` | machine paths, account notes |
| OpenCode data | `%USERPROFILE%\.local\share\opencode\` | `auth.json`, `opencode.db` |
| Caches / build artifacts | `__pycache__/`, `*.pyc`, `egg-info/`, `.pytest_cache/` | embed local absolute paths |
| Secret-looking files | `.env*`, `*.pem`, `*.key`, `auth.json`, `*.db` | credentials/data |
| Obsidian vault | user-chosen path | personal notes |

**Never read by AIOS:** `auth.json`, `mcp-auth.json` (provider API keys).

## Enforced by

1. **Default location outside the repo** — `projects_root` defaults to
   `~/.aios/projects`; the repository contains no runtime data directory.
2. **`.gitignore`** — guards the repo-local fallback too (local config,
   caches, secret-shaped files). Verified at runtime via
   `git check-ignore` inside `aios security-audit`.
3. **`aios security-audit`** — scans working tree, Git index, and Git
   history for: private paths, personal filesystem paths
   (`C:\Users\<name>`), secret patterns (AWS/GitHub/OpenAI/Google/Slack
   keys, private-key blocks, JWTs), and risky tracked files. Reports
   `PASS` / `WARNINGS` / `FAIL`; never prints secret values.
4. **Read-only history boundary** — OpenCode SQLite opened with
   `?mode=ro`; transcripts via official `opencode export` only.

## Git history rule

A clean working tree is **not enough**: if any commit ever contained
private data (`projects/`, run logs, personal paths, credentials), the
history itself is private and **must be rewritten (squashed/orphan
branch) before the first push**. `aios security-audit` checks this and
fails with `history exposure` until the published history is clean.

## Before every publication

Run in order:

```powershell
aios security-audit     # must report PASS
git status              # nothing unexpected staged
```

If the audit fails on `history exposure`, publish from a squashed or
orphan branch — never push the original history.
