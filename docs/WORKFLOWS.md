# WORKFLOWS

## Classification

`aios start "<task>"` first classifies the task into one or more task
types (`src/aios/task_types.py`), then selects exactly one workflow:

| Priority | Workflow | Trigger types | What runs |
|---------:|----------|---------------|-----------|
| 1 | HUMAN_REVIEW | human input needed | no agent; state set to `human_review` |
| 2 | HISTORY | history/ideas from past sessions | archives sessions → one history agent → `Ideas.md` |
| 3 | REVIEW | review-only request | one review agent → `REVIEW.md` verdict |
| 4 | BUILD_LOOP | build/code/test/fix | build → review → (fix → review) until PASS or limit |
| 5 | KNOWLEDGE | research/analysis | one agent → `RESEARCH.md` / notes |
| 6 | BUILD_LOOP (default) | anything else | same as build loop |

Multi-intent tasks are allowed (e.g. `"research X and summarize"` →
`types=[ANALYSIS, RESEARCH]`, workflow `KNOWLEDGE`).

## Capability routing

Each workflow needs a capability (`build`, `review`, `fix`, `history`,
`research`, ...). The registry (`src/aios/agents/registry.py`) resolves
capability → first enabled agent that has it, breaking ties by role
(reviewer > builder for review, fixer > builder for fix). Project-level
`enabled_agents` narrows the candidate set.

Adding a new agent = add an entry under `agents:` in config. No code
changes.

## BUILD_LOOP phases

```
build ──► review ──PASS──────────────► COMPLETE
  ▲          │
  │          ├──FAIL──────────► fix ──► review (repeats)
  │          │
  │          └──NEEDS_HUMAN_REVIEW──► human_review
  └── run failure ──► FAILED
```

- A stale `REVIEW.md` is deleted before every review run so an old
  verdict can never satisfy a new review.
- The reviewer must write `REVIEW.md` containing a `## Final Status`
  line (`PASS` / `FAIL` / `NEEDS_HUMAN_REVIEW`); no verdict = ERROR.
- `max_iterations` (default 5) caps build/fix cycles.
- The prompt template follows the PHASE (build/review/fix), not the
  agent name — whoever reviews gets the review contract.

## Agent contract

Every prompt ends with the AIOS contract: the agent must write
`AIOS_REPORT.json` (`status`, `summary`, `files_changed`, `errors`,
`next_recommended_action`, ...). If the file is missing, AIOS falls back
to exit-code status and records that the report was not structured.

## Evidence

State lives in Markdown under `projects/<name>/` (see MEMORY.md) and raw
per-run logs under `projects/<name>/Runs/`.
