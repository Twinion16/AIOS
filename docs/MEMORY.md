# MEMORY

AIOS keeps all shared memory as Markdown per project, optionally mirrored
into an Obsidian vault.

## Location

- Project state: `projects/<name>/` (root configurable via
  `projects_root`)
- Obsidian mirror: `<obsidian_vault_path>/Projects/<name>/` — enabled only
  when the vault path is set in `config/config.yaml`; mirrors are copies
  (Obsidian never becomes the only copy)
- Run history: `projects/<name>/Runs/` (prompts, logs, reports, rotated
  `AIOS_REPORT.json`)

## State files

| File | Purpose |
|------|---------|
| `PROJECT.md` | project definition |
| `CURRENT_STATE.md` | current truth: status, workflow, task types, iteration, current agent, review verdict |
| `TASK.md` | the active task (with project/workflow/type placeholders) |
| `HANDOFF.md` | agent-to-agent handoff notes |
| `REVIEW.md` | reviewer verdict (`## Final Status`: PASS/FAIL/NEEDS_HUMAN_REVIEW) — deleted before each review run |
| `DECISIONS.md` | decision log |
| `TODO.md` | task tracking |
| `RESEARCH.md` | research/analysis findings |
| `Ideas.md` | extracted knowledge from past sessions (HISTORY workflow) |

## Rules

- **Never invent status**: unknown facts are written as `UNKNOWN`.
- **HISTORY ≠ MEMORY**: `History/OpenCode/*.md` are raw archived session
  transcripts; `Ideas.md` is the extracted, dated, evidenced knowledge.
  Archives are evidence, ideas are conclusions.
- **Read-only history**: OpenCode history is read via `opencode db` /
  `opencode export` only. AIOS never writes `opencode.db`, never touches
  `-wal`/`-shm`, never runs `opencode session delete`.
- Writes are additive; `TASK.md` is the only file a new task overwrites.
