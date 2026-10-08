# OpenCode History — Audit

Date of audit: 2026-10-08
OpenCode version audited: **1.18.34** (npm install, Windows x64)
All facts below were verified against the installed environment. Nothing is
assumed or invented.

## 1. Installation facts

| Item | Verified value | How verified |
|---|---|---|
| Version | `1.18.34` | `opencode --version` |
| Executable | npm shim `%APPDATA%\npm\opencode.ps1` → `node_modules\@opencode\cli\bin\opencode.exe` | `Get-Command opencode`, shim source |
| Config file | `%USERPROFILE%\.config\opencode\opencode.jsonc` | inspected (plugins + canva MCP only) |
| Data directory | `%USERPROFILE%\.local\share\opencode\` | directory listing |

Data directory contents:

```
%USERPROFILE%\.local\share\opencode\
├── auth.json          # credentials — NEVER read or copied by AIOS
├── mcp-auth.json      # credentials — NEVER read or copied by AIOS
├── log\
├── opencode.db        # SQLite history database  ← session history
├── opencode.db-shm    # WAL shared memory
├── opencode.db-wal    # WAL journal
├── repos\
├── snapshot\          # file snapshots (undo/rewind data)
└── tool-output\
```

**Secrets note:** `auth.json` and `mcp-auth.json` contain provider API keys.
AIOS history access must never open them.

## 2. Where history actually resides

History lives in a single SQLite database: `opencode.db`.

Verified by the official CLI:

```
> opencode db path
%USERPROFILE%\.local\share\opencode\opencode.db
```

Current scale (SQL `COUNT(*)`, 2026-10-08):

| Table | Rows |
|---|---|
| `session` | 48 |
| `message` | 1577 |
| `part` | 5761 |
| `part` rows containing the word "idea" | 338 |

## 3. Relevant schema (from `sqlite_master`)

```sql
CREATE TABLE session (
  id text PRIMARY KEY,          -- e.g. ses_f5744ad8affe8G1VPfu2Nr5WKq
  project_id text NOT NULL,     -- 'global' for local sessions
  parent_id text,
  slug text NOT NULL,           -- e.g. 'witty-island' (human-readable handle)
  directory text NOT NULL,      -- cwd when the session ran
  title text NOT NULL,          -- often auto: "New session - <ISO date>"
  version text NOT NULL,        -- opencode version that created it
  time_created integer,         -- epoch milliseconds
  time_updated integer,
  ...
);

CREATE TABLE message (
  id text PRIMARY KEY,
  session_id text NOT NULL,     -- FK → session.id
  time_created integer,
  time_updated integer,
  data text NOT NULL            -- JSON: {"role","time","agent","model","summary"}
);

CREATE TABLE part (
  id text PRIMARY KEY,
  message_id text NOT NULL,     -- FK → message.id
  session_id text NOT NULL,
  time_created integer,
  data text NOT NULL            -- JSON: {"type":"text"|"reasoning"|"step-start"|...,
                                --        "text":"..."}
);
```

### How sessions are identified

- Session id: `ses_<26 chars>` (stable, primary key, safe for filenames after
  normalisation).
- Session slug: short word-handle (e.g. `witty-island`).
- Sessions are NOT scoped to a project directory in practice: sessions recorded
  here have `project_id = 'global'` and a `directory` field (e.g.
  `C:\Windows\System32`). There is no per-repository session partition to rely
  on; filtering must use `directory`, `title`, and message content.

### How messages can be retrieved

Message content is split across two tables:

- `message.data` → role (`user` / `assistant`), agent, model, timestamps.
- `part.data` → the actual content: `type` ∈ {`text`, `reasoning`,
  `step-start`, tool payloads...}; `text` holds the prose for `text` and
  `reasoning` parts.

Verified example (schema shape only — actual session content is private and
not reproduced here):

- user text part: `<user's question or instruction>`
- assistant `reasoning` part and `text` parts follow.

To rebuild a conversation: `session` → `message` (by `session_id`) → `part`
(by `message_id`), ordered by `time_created`.

## 4. Official CLI/API mechanisms (verified with `--help`)

These are official, documented-by-help-text commands for this installed
version. AIOS must use them rather than inventing an API:

| Command | Purpose | Verified output |
|---|---|---|
| `opencode session list` | list sessions | `ses_<id>  <title>  <time>` rows |
| `opencode session delete <id>` | delete a session | exists (AIOS must never call it) |
| `opencode export <sessionID>` | export one session as JSON | JSON object `{info, messages[]}`, each message has `info.role` and `parts[]` with `type`/`text` |
| `opencode export <id> --sanitize` | redacted export | flag exists |
| `opencode db "<sql>" --format json` | run arbitrary SQL | JSON array of rows |
| `opencode db path` | print DB path | absolute path |
| `opencode db` | interactive sqlite3 shell | exists |
| `opencode import <file>` | import session JSON | exists |

Notes / limitations:

- `opencode export` prints `Exporting session: <id>` on **stderr** and JSON on
  **stdout**; parsers must read stdout only.
- `opencode db` opens the same SQLite file; while OpenCode is running, the DB
  is in WAL mode (`-shm`/`-wal` files exist). Concurrent read access is
  allowed, but AIOS must open the DB **read-only** and must never write,
  migrate, or vacuum it.
- There is no official "search across sessions" command in 1.18.34. Search is
  implemented by AIOS (SQL `LIKE` over `part.data`, or reading exported JSON).
- Session list output format is not machine-stable (columns are padded text);
  for structured data prefer `opencode db "<sql>" --format json` or
  `opencode export`.

## 5. Safe programmatic access — decision

Two verified access paths, both read-only:

1. **Direct SQLite read (primary).** `sqlite3.connect('file:<path>?mode=ro', uri=True)`
   against the path from `opencode db path` (fallback: the well-known data
   directory). Read-only connection, no schema changes, no writes. Fast for
   search across all 48 sessions.
2. **Official CLI export (traceable source).** `opencode export <id>` → JSON on
   stdout, used when an exact official transcript of one session is needed.

Both are wrapped behind AIOS's `HistoryProvider` abstraction so the
orchestrator never touches storage internals:

```
AIOS → HistoryProvider → OpenCodeHistoryProvider → opencode.db / opencode export
```

## 6. Limitations (must be respected by every consumer)

- No full-text index (no FTS5 table exists) — search is substring/keyword
  matching, not semantic search.
- `title` is usually auto-generated (`New session - <date>`), so titles are
  weak signals; content must be searched too.
- Timestamps are epoch **milliseconds** in local-session rows but the export
  nests them as `{created, updated}` — normalise before comparing.
- Sessions are global, not per-project. AIOS must not claim a session belongs
  to a project unless `directory`/content supports it; otherwise mark project
  affiliation as `UNKNOWN`.
- Message `data` JSON shape may change across opencode versions (rows record
  `version` on sessions, e.g. `1.18.30` vs current `1.18.34`). The provider
  must tolerate missing/extra keys and never assume fields exist.
- History proves what was *said*, not what was *done*. Implementation status of
  an idea is `UNKNOWN` unless the transcript or project files explicitly show
  it.

## 7. Version-specific considerations

- Written for OpenCode **1.18.34**; DB path resolution prefers
  `opencode db path` so it keeps working if the data directory moves.
- If a future version renames tables/columns, `OpenCodeHistoryProvider` must
  degrade gracefully: report `HistoryProviderError` with a clear message rather
  than crashing the orchestrator, and re-run the audit before patching.
- `opencode.db-wal` must be left untouched; read-only connections replay WAL
  safely for readers.

## 8. What AIOS must NOT do

- Do not hard-code the DB path as the only source (use it only as fallback).
- Do not write to `opencode.db`, and do not touch `-shm`/`-wal`.
- Do not read `auth.json` / `mcp-auth.json`.
- Do not call `opencode session delete`.
- Do not invent methods not present in `--help` (there is no documented
  session-search or messages API in 1.18.34 beyond `export` and `db`).
- Do not flatten transcripts into project memory: raw history and extracted
  knowledge are stored separately (see `docs/MEMORY.md`).
