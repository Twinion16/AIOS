# AIOS

Multi-agent AI orchestration with a shared Markdown memory layer.
Classifies a natural-language task, picks a workflow, routes it to the
right agent by capability, and keeps every step verifiable in files.

```
                 ┌─────────────────────────────────────────────┐
                 │                  aios CLI                   │
                 │  start / status / project / history /       │
                 │  security-audit                             │
                 └──────────────────────┬──────────────────────┘
                                        │
        ┌───────────────────────────────▼───────────────────────────────┐
        │                        Orchestrator                          │
        │  classify task → select workflow → phase loop                │
        │  BUILD → REVIEW → (FIX → REVIEW)*   or   HISTORY / KNOWLEDGE │
        └───┬───────────────┬────────────────┬─────────────────┬───────┘
            │               │                │                 │
   ┌────────▼───────┐ ┌─────▼──────┐ ┌───────▼───────┐ ┌───────▼────────┐
   │ AgentRegistry  │ │ ContextEngine│ │ ProjectRegistry│ │ HistoryProvider│
   │ capability →   │ │ task-type →  │ │ name → state  │ │ READ-ONLY      │
   │ agent + prompt │ │ prompt bundle│ │ dir + repo    │ │ opencode.db    │
   └────────┬───────┘ └─────────────┘ └───────────────┘ └────────────────┘
            │
   ┌────────▼──────────────────────────────────────────────────────────┐
   │ agents (subprocess): opencode ✓ │ hermes (disabled) │ kilo (off) │
   └───────────────────────────────────────────────────────────────────┘

Private runtime data (state, run logs, history archives) lives in
~/.aios/projects — never in the source repository (see docs/PUBLIC_VS_PRIVATE.md).
```

## Install

```powershell
cd path\to\AIOS
pip install -e .
```

Requires Python 3.12+ and `opencode` on PATH (the only agent with working
credentials today — see "Agent status").

## Usage

```powershell
# start a task (task must be ONE quoted argument)
aios start "Build the first MVP of my wallpaper fitting tool"
aios start --project my-project "Add a search box to the homepage"

# project registry
aios project list
aios project create my-project --repository C:\code\my-project

# read-only OpenCode history (strictly no writes, no deletes)
aios history list
aios history search "wallpaper ideas"

# status of all projects
aios status
```

Every run prints an `Intent:` line (classified task types + workflow) and
ends with an explicit `Final state:` (COMPLETE / FAILED / HUMAN_REVIEW /
ERROR) plus the agent's structured report.

## Configuration

Auto-loaded in this order: `--config <path>` > `$AIOS_CONFIG` >
`./config/config.yaml` > `~/.aios/config.yaml` > built-in defaults
(deep-merged).

| File | Owner | Purpose |
|------|-------|---------|
| `config/config.yaml` | you | agents, history, timeouts, vault path — AIOS never rewrites it |
| `config/projects.yaml` | AIOS | generated project registry (repository/vault/enabled agents) |

Key settings:

- `projects_root` — where project state lives; **default
  `~/.aios/projects`** (private runtime data stays outside the repository)
- Relative paths (`projects_root`, `obsidian_vault_path`) are anchored to
  the AIOS package root, never the shell's current directory — `aios`
  behaves the same from any directory
- `obsidian_vault_path` — vault root; project notes mirror to
  `<vault>/Projects/<name>/` (empty = Markdown-only, no mirroring)
- `agents.<name>.enabled` — flip to `true` once that agent authenticates
- `agents.<name>.executable` — override binary; may be multi-token
  (`python {root}\path\wrapper.py`; `{root}` = AIOS repo root) for test
  stubs/wrappers
- `history.opencode.*` — read-only session history (db auto-detected via
  `opencode db path`)

## Agent status (verified 2026-10-08)

| Agent | Status | Notes |
|-------|--------|-------|
| opencode | working | build + review + fix + research + history |
| hermes | disabled | Nous Portal account has $0.00 credits — every model fails |
| kilo | disabled | not signed in (`kilo` prompts for login) |

Routing is capability-based, so opencode covers review/fix meanwhile.
Re-enable hermes/kilo in `config/config.yaml` once their credentials work;
no code changes needed.

## Tests / acceptance evidence

```powershell
# full BUILD -> REVIEW -> FIX loop with a deterministic stub reviewer
# (FAIL first review, then PASS): tests/config.fixtest.yaml
aios start --config tests\config.fixtest.yaml --project loop-fix2 "Create greeter.py with tests"

# HISTORY retrieval from OpenCode sessions
aios start --project history-test "Find ideas discussed in previous OpenCode sessions"
```

Test helpers: `tests/stub_agent.py` (stub wrapper), `tests/config.*.yaml`.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 AIOS contributors.

## Security & privacy

- Private runtime data (project state, run logs, agent prompts, history
  archives) lives under `~/.aios/projects`, **outside** the repository.
- Only `config.example.yaml` is public; `config/config.yaml` and
  `config/projects.yaml` are gitignored machine-local files.
- OpenCode history access is **strictly read-only** (`mode=ro` SQLite +
  official `opencode export`); credentials (`auth.json`) are never opened.
- Before any publication run the built-in audit (read-only):

```powershell
aios security-audit        # scans working tree, git index, and git history
```

See [docs/PUBLIC_VS_PRIVATE.md](docs/PUBLIC_VS_PRIVATE.md) for the full
public/private boundary.

## Documentation

- [docs/AIOS_CURRENT_STATE.md](docs/AIOS_CURRENT_STATE.md) — status snapshot: what works, what is not active
- [docs/OPENCODE_HISTORY.md](docs/OPENCODE_HISTORY.md) — history schema, access, limits
- [docs/WORKFLOWS.md](docs/WORKFLOWS.md) — workflows and routing
- [docs/AGENTS.md](docs/AGENTS.md) — agent registry and prompts
- [docs/MEMORY.md](docs/MEMORY.md) — state files and Obsidian memory
- [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md) — Windows setup details
- [docs/PUBLIC_VS_PRIVATE.md](docs/PUBLIC_VS_PRIVATE.md) — what may be published vs what stays private
- [docs/PUBLIC_RELEASE_CHECKLIST.md](docs/PUBLIC_RELEASE_CHECKLIST.md) — release gate status
- [docs/GITHUB_WORKFLOW.md](docs/GITHUB_WORKFLOW.md) — safe branch strategy: private `master` vs public `publish` → GitHub `main`
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ENVIRONMENT_AUDIT.md](docs/ENVIRONMENT_AUDIT.md)
