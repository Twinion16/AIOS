# SETUP (Windows)

## Prerequisites

- Windows 10/11, PowerShell 5.1+
- Python 3.12+ on PATH (`python --version`)
- [OpenCode](https://opencode.ai) on PATH (`opencode --version`) — the
  only agent with working credentials today

## Install AIOS

```powershell
cd path\to\AIOS
pip install -e .
aios --help
```

## Configure

```powershell
copy config\config.example.yaml config\config.yaml
```

Edit at minimum:

1. `obsidian_vault_path` — your vault root (leave `""` to skip mirroring)
2. `agents.*.enabled` — leave hermes/kilo `false` until fixed:
   - hermes: needs Nous Portal credits (verified $0.00 on 2026-10-08);
     check with `hermes chat -q "ping" --oneshot`
   - kilo: needs `kilo` sign-in (currently "You need to sign in to use
     this model")

Projects you create (`aios project create`) are written to
`config/projects.yaml`; `config/config.yaml` itself is never rewritten.

## Verify

```powershell
aios project list
aios history list
aios history search "wallpaper"
aios start --project smoke-test "Create a hello.py that prints Hello and a pytest test"
aios status
```

Expected: `Intent:` line, agent runs, `Final state: COMPLETE`, files under
`projects\smoke-test\`.

## Troubleshooting

- **`python : SyntaxWarning` / encoding crashes** — the CLI forces
  `errors=replace` on stdout/stderr; if you embed AIOS as a library, set
  your own reconfigure.
- **Hermes 404 / "no credits"** — Nous Portal subscription empty; disable
  the agent or add credits at portal.nousresearch.com/billing.
- **Kilo "need to sign in"** — run kilo's login flow, then set
  `agents.kilo.enabled: true`.
- **History db not found** — AIOS resolves it via `opencode db path`;
  override with `history.opencode.db_path` if opencode is not on PATH.
