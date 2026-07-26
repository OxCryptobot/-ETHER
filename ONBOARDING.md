# @ETHER — Cousin / partner onboarding (one page)

## What this is

Local-first **verified** coding agent: plan → code (local LLM, optional cloud burst) → sandbox → audit → gate → learn.

Not a claim that it beats Cursor/Claude Code. Scoreboard numbers only.

## Machine setup (Windows)

1. Install: **Git**, **Python 3.11+**, **Docker Desktop**, **Ollama**
2. Pull a small coder model:
   ```powershell
   ollama pull qwen2.5-coder:3b
   ollama pull nomic-embed-text
   ```
3. Clone & venv:
   ```powershell
   git clone https://github.com/OxCryptobot/-ETHER.git
   cd -ETHER
   python -m venv .venv
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```
4. Env:
   ```powershell
   copy .env.example .env
   # ETHER_PRIMARY_MODEL=qwen2.5-coder:3b
   ```
5. Smoke:
   ```powershell
   python scripts\smoke_test.py
   pytest -q
   python -m cli.main doctor
   python -m cli.main run "write a python function is_even(n) with assert is_even(4)"
   ```

## One window autonomy

```powershell
$env:ETHER_GIT_RESET_OK = "1"
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

Dashboard: http://127.0.0.1:8787

## Optional burst

Keys only in local `.env` — never commit.

## Golden rules

1. Use venv / `python -m cli.main`.
2. Hard reset only with intent (`ETHER_GIT_RESET_OK=1`).
3. Trust `SCOREBOARD.md`, not adjectives.
4. Quarantine tools are untrusted until reconcile.
