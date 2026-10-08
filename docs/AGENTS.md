# AGENTS

Agents are declared in config (`agents:` section) and resolved at run
time by capability — see WORKFLOWS.md for routing rules.

## Registry

| Agent | Role | Capabilities | Default | Status (2026-10-08) |
|-------|------|--------------|---------|---------------------|
| opencode | builder | build, fix, test, research, analysis, history, documentation, planning, new_project, review | enabled | working |
| hermes | reviewer | review, research, analysis | **disabled** | broken: Nous Portal $0.00 credits |
| kilo | fixer | fix, build, test | **disabled** | broken: not signed in |

Config knobs per agent:

- `role` — tie-breaker when several agents share a capability
- `executable` — binary to run; multi-token values are supported
  (`python C:\path\wrapper.py`) and stay inside python.exe, so prompts
  with quotes/`<`/`>` are never re-parsed by cmd.exe
- `capabilities` — what the agent may be scheduled for
- `enabled` — hard off switch (disabled agents are invisible to routing)

## How each agent is invoked

| Agent | Command shape | Working dir |
|-------|---------------|-------------|
| opencode | `opencode run <prompt>` | project repository, else state dir |
| hermes | `hermes chat --query-file <prompt> --oneshot -Q` (fallback `-q`) | same |
| kilo | `kilo run <prompt>` | same |

Model/provider overrides: `agent_options.hermes.model` /
`agent_options.hermes.provider`.

## Prompts

Templates in `src/aios/prompts/` are selected by workflow + phase
(+ agent role as fallback):

- `opencode_build.md` — BUILD phase contract (files + HANDOFF ready)
- `hermes_review.md` — REVIEW phase contract (writes `REVIEW.md`)
- `kilo_fix.md` — FIX phase contract (fix reported items, never stamps verdicts)
- `opencode_history.md` — history extraction → `Ideas.md`
- `opencode_research.md` / `opencode_analysis.md` — knowledge work
- `history_retrieval.md` — HISTORY manifest rendering

Every prompt receives `{task}`, `{project_dir}`, `{context_files}`,
`{context_summary}` (and `{history_manifest}` where relevant), plus the
append-only `AIOS_REPORT.json` contract.

## Test doubles

`tests/stub_agent.py` stands in for an agent executable during acceptance
tests: it delegates BUILD prompts to real opencode, FAILs the first
REVIEW, records FIX runs, then PASSes the re-review. Point
`agents.<name>.executable` at `python <path>\stub_agent.py` and disable
the real reviewers (see `tests/config.fixtest.yaml`).
