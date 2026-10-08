# AIOS — Current State (Status Snapshot)

Date of last update: 2026-10-08
Audited version: AIOS 0.1.0 (`pip install -e .`, entry point `aios`)
OpenCode: 1.18.34 (verified via `opencode --version`)

## 1. What works today

The full orchestration chain is verified live on Windows:

```
Windows Terminal
  → aios (click CLI)
    → Python (AIOS orchestrator)
      → opencode.exe (subprocess via subprocess.run)
        → opencode child process
```

Verified behaviours (each proven by an actual run, not by inspection):

- `aios start "<task>" --project <name>` classifies intent, selects a
  workflow, and prints `Intent:` + final `Final state:`
  (COMPLETE / FAILED / HUMAN_REVIEW / ERROR) with the agent's structured
  `AIOS_REPORT.json`.
- BUILD → REVIEW → FIX loop terminates on **both** paths: real PASS and
  deterministic FAIL → fix → PASS (stub reviewer).
- HISTORY retrieval answers "ideas discussed in previous OpenCode
  sessions" and archives raw sessions under
  `~/.aios/projects/<name>/History/OpenCode/` (read-only access).
- RESEARCH / KNOWLEDGE tasks produce `RESEARCH.md` from multiple web
  sources without touching code paths.
- Standalone REVIEW writes a verdict file with FAIL/PASS semantics.
- `aios history list|search` reads OpenCode sessions read-only
  (`mode=ro` SQLite + official `opencode export`).
- `aios security-audit` scans tree/index/history for secrets, private
  data, and personal paths (read-only, never prints secret values).
- Private runtime data lives outside the repository
  (`~/.aios/projects`); config files are never rewritten by AIOS.

## 2. Test status by area

| Area | Status | Evidence |
|------|--------|----------|
| Task classification & workflow routing | **working** | `tests/verify.py` classification block |
| Config loading (no rewrite, path anchoring) | **working** | `tests/verify.py`; config.yaml untouched across runs |
| Agent registry & capability routing | **working** | `tests/verify.py` resolve/prompt checks |
| Phase-aware prompts | **working** | `tests/verify.py` prompt-name checks |
| BUILD → REVIEW → FIX (PASS path) | **working** | `loop-test` project, real opencode |
| BUILD → REVIEW → FIX (FAIL→fix→PASS) | **working** | `loop-fix2` project, stub reviewer + real pytest |
| HISTORY retrieval + archiving | **working** | `history-test` project, 8 sessions archived |
| RESEARCH / KNOWLEDGE workflow | **working** | `research-test` project, 11 sources |
| Standalone REVIEW | **working** | verdict file written (FAIL semantics) |
| End-to-end diag project | **working** | `diag-test`, review PASS, `1 passed` |
| OpenCode history (read-only) | **working** | `aios history list/search`, `mode=ro` proven |
| Obsidian mirroring | **not active** | no vault on this machine (`obsidian_vault_path: ""`) |
| Hermes as reviewer | **not active** | disabled: Nous Portal account has $0.00 credits |
| Kilo as fixer | **not active** | disabled: not signed in |
| Publish to GitHub | **not active** | forbidden until human approval; see docs/PUBLIC_RELEASE_CHECKLIST.md |

## 3. Current source layout

```
src/aios/
├── cli.py               # start, status, project, history, security-audit
├── config.py            # defaults + YAML loader (deep merge, ~/.aios fallback)
├── task_types.py        # classify_task / select_workflow / describe_task
├── orchestrator.py      # phase loop: BUILD → REVIEW → (FIX → REVIEW)*
├── state_machine.py     # TaskState enum
├── persistence.py       # Obsidian-style state file helpers
├── reporting.py         # AIOS_REPORT.json contract
├── projects.py          # ProjectRegistry (state dirs, create/list)
├── security_audit.py    # read-only publish-readiness audit
├── agents/
│   ├── base.py          # BaseAgent ABC, {root}/env executable expansion
│   ├── registry.py      # capability → agent + prompt-template routing
│   ├── opencode.py      # opencode run "<prompt>"
│   ├── hermes.py        # hermes chat --query-file ... (disabled)
│   └── kilo.py          # kilo run "<prompt>" (disabled)
├── history/
│   ├── base.py          # HistoryProvider abstraction
│   └── opencode_history.py  # read-only sqlite + `opencode export`
├── context/
│   ├── engine.py        # task-type → context bundle + prompt selection
│   ├── loader.py        # state file reading (legacy)
│   └── writer.py        # template copying (legacy)
├── execution/process.py # subprocess wrapper (timeout, capture)
├── obsidian/vault.py    # vault helper (used when a vault is configured)
└── prompts/*.md         # phase-aware prompt templates
templates/               # PROJECT/TASK/REVIEW/... markdown skeletons
tests/                   # verify.py battery, stub_agent, loop configs
```

## 4. Execution flow

```
aios start "<task>" [--project P]
  ├─ load config (defaults + config.yaml, never rewritten)
  ├─ classify_task → select_workflow → print Intent
  ├─ workflow == BUILD_LOOP:
  │    loop (max_iterations):
  │      build  → opencode_build.md  → agent run → Runs/ + report
  │      review → hermes_review.md   → REVIEW.md verdict
  │      ├─ PASS            → COMPLETE
  │      ├─ NEEDS_HUMAN...  → HUMAN_REVIEW
  │      └─ FAIL            → fix → re-review
  ├─ workflow == HISTORY / RESEARCH / ANALYSIS / KNOWLEDGE:
  │    context bundle (history manifest / source notes) → agent → report
  └─ Final state printed (COMPLETE / FAILED / HUMAN_REVIEW / ERROR)
```

## 5. Former limitations L1–L9 — all fixed

| # | Limitation | Resolution |
|---|-----------|------------|
| L1 | every task treated as BUILD | `task_types.py` classification + workflow selection |
| L2 | no history-retrieval architecture | `HistoryProvider` + HISTORY workflow + archives |
| L3 | implicit project selection | `ProjectRegistry`, `--project`, `aios project create` |
| L4 | templates overwritten every run | only TASK/contract rewritten; state files persist |
| L5 | hard-coded agent routing | `AgentRegistry`, capability-based routing |
| L6 | no structured output contract | `AIOS_REPORT.json` appended to every prompt |
| L7 | hermes environmentally broken | disabled by default; opencode covers all capabilities |
| L8 | HISTORY vs MEMORY conflated | raw `History/` archives vs extracted `Ideas.md` |
| L9 | no knowledge-vs-code distinction | HISTORY/KNOWLEDGE workflows, knowledge outputs |

## 6. Verified environment facts

| Item | Value | Evidence |
|---|---|---|
| OpenCode version | 1.18.34 | `opencode --version` |
| OpenCode executable | `%APPDATA%\npm\opencode.exe` (npm shim) | process tree + npm shim |
| OpenCode config | `%USERPROFILE%\.config\opencode\opencode.jsonc` | present on disk |
| OpenCode data dir | `%USERPROFILE%\.local\share\opencode\` | listed |
| History database | `%USERPROFILE%\.local\share\opencode\opencode.db` (SQLite, WAL) | `opencode db path` |
| Official history CLI | `opencode session list`, `opencode export <id>`, `opencode db "<sql>" --format json` | `opencode --help` |
| Python | 3.12.10 | `python --version` |
| Shell | PowerShell 5.1 | env |

See `docs/OPENCODE_HISTORY.md` for the full history-storage audit.

## 7. Known constraints

- PowerShell 5.1: no `&&`, no heredocs, no `head`/`tail`/`grep` here.
- Files written through PowerShell here-strings gain a BOM that breaks
  TOML/YAML; Python file writes must use UTF-8 without BOM.
- Long agent runs (2–5 min) exceed the default 120 s shell timeout;
  test commands need explicit larger timeouts.
- `aios start` accepts the task as ONE quoted argument; unquoted
  multi-word input yields `Error: Got unexpected extra arguments`.
- `.cmd` agent shims re-parse prompts through cmd.exe; multi-token
  `executable` values (`python {root}\...`) keep prompts inside python.

## 8. Correction spec status

All 13 correction steps: **DONE and verified** (see section 1–2).
Publish preparation (privacy boundary, sanitization, security-audit,
fresh-clone test): done locally; **push/publication requires explicit
human approval** — see `docs/PUBLIC_RELEASE_CHECKLIST.md`.
