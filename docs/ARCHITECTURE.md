# ARCHITECTURE.md

## AIOS Architecture

### Core Principle
Obsidian is the shared memory layer. Agents read/write Markdown state files to collaborate.

### Components

1. **Orchestrator** (src/aios/orchestrator.py) - Workflow dispatch, state machine, agent invocation
2. **Task classification** (src/aios/task_types.py) - task types + workflow selection
3. **Agent registry** (src/aios/agents/) - capability -> agent routing (opencode, hermes, kilo)
4. **Context engine** (src/aios/context/engine.py) - context bundle, history archives, prompt rendering
5. **History provider** (src/aios/history/) - read-only OpenCode session access
6. **Memory** (src/aios/persistence.py) - Markdown state files + Obsidian mirror
7. **Reporting** (src/aios/reporting.py) - AIOS_REPORT.json contract
8. **Projects** (src/aios/projects.py) - explicit project registry

### State Flow
NEW_TASK -> classified workflow (see WORKFLOWS.md):
  BUILD_LOOP: BUILDING -> REVIEWING ->
    - COMPLETE if PASS
    - FIXING if FAIL, then back to REVIEWING (max_iterations cap)
    - HUMAN_REVIEW if NEEDS_HUMAN_REVIEW
  HISTORY: RETRIEVING -> COMPLETE (Ideas.md)
  KNOWLEDGE: one agent run -> COMPLETE
Agents are picked by capability, not hardcoded (today opencode covers
build/review/fix; hermes/kilo are disabled pending credentials).

### Shared State Files
- PROJECT.md - Project definition
- CURRENT_STATE.md - Current truth (status, iteration, agents)
- TASK.md - Current task
- HANDOFF.md - Agent handoff communication
- REVIEW.md - Review results
- DECISIONS.md - Decision log
- TODO.md - Task tracking
- RESEARCH.md - Research notes
- Runs/*.md - Historical logs
