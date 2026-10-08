# PUBLIC RELEASE CHECKLIST — AIOS

Gate: every box must be checked (or consciously waived by a human)
before the repository is pushed to GitHub. `aios security-audit` must
report `PASS`.

## 1. Privacy boundary

- [x] Runtime data lives outside the repo (`~/.aios/projects` default)
- [x] Existing runtime data migrated out of the repository
- [x] `config/config.yaml` + `config/projects.yaml` gitignored; only
      `config.example.yaml` public with placeholder paths
- [x] `.gitignore` covers projects/runs/history, caches, secret-shaped
      files (verified with `git check-ignore`)
- [x] No real usernames or `C:\Users\<name>` paths in any public file
- [x] No private conversation text in docs (history examples genericized)

## 2. Secrets

- [x] No credential files in tree (`.env`, `auth.json`, keys, dbs)
- [x] Secret-pattern scan of working tree + index: clean
- [x] Secret-pattern scan of git history: clean
- [x] AIOS never reads `auth.json` / `mcp-auth.json` (documented + coded)

## 3. Git state

- [x] Private/generated files untracked (`projects/**`, `*.pyc`,
      `__pycache__`, `egg-info`)
- [x] No git remotes configured (nothing ever pushed)
- [ ] **History is clean** — FAIL today: original commit contains
      private runtime data → publish via orphan/squash branch only
- [x] Fresh-clone test passes as a new user (depth-1 clone → install →
      verify → security-audit)

## 4. Correctness (from the correction spec)

- [x] BUILD → REVIEW → FIX verified on both PASS and FAIL paths
- [x] HISTORY retrieval verified (read-only, archives under `History/`)
- [x] RESEARCH / KNOWLEDGE workflow verified
- [x] Standalone REVIEW verified
- [x] End-to-end diag test verified (pytest green in run)
- [x] `tests/verify.py` — full battery green (portable, no private data)

## 5. Documentation

- [x] README: overview, diagram, install, usage, config, security, links
- [x] `docs/PUBLIC_VS_PRIVATE.md` — explicit boundary
- [x] `docs/PUBLIC_RELEASE_CHECKLIST.md` — this file
- [x] `docs/AIOS_CURRENT_STATE.md` — status snapshot (working / not active)
- [x] Agent status accurate (opencode working; hermes/kilo disabled)

## 6. Open decisions (human approval required)

- [x] **License chosen and LICENSE file added** — MIT, approved 2026-10-08;
      copyright "AIOS contributors" (no personal information)
- [ ] GitHub repo name / visibility decided
- [x] Whether to keep or delete the private `master` history locally —
      kept local-only, never pushed
- [ ] Explicit human approval to push (nothing may be pushed until then)

## 7. Release commands (for later — NOT executed yet)

```powershell
# from a clean orphan/publish branch containing only public files:
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin publish:main
```

Status: **READY_FOR_PUSH** — all technical/privacy gates green on the
`publish` branch (fresh-clone PASS, security-audit PASS, MIT LICENSE
added). Publication itself still awaits the explicit push instruction
(section 6); only the `publish` branch may ever be pushed.
