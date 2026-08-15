# Local recovery (Windows)

## Preferred path (host agent live)

When Grok reports **stale heartbeat** or pending jobs not draining:

```powershell
cd C:\Users\Otcde\ETHER
powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1
```

Hard recovery (broken venv / `ModuleNotFoundError`):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1 -Hard
```

What `recover_host.ps1` does:

1. Kill stale `ether_host` / `host_agent` / dashboard python
2. `git merge --abort` + `fetch` + `reset --hard origin/main`
3. Quarantine stuck live/ledger jobs from `artifacts/jobs/pending/` → `failed/`
4. Optional `-Hard`: recreate `.venv` + `pip install -e ".[dev]"`
5. Hand off to `start_ether_host.ps1` self-healing loop (exit 0 = stop, 42 = reload, other = backoff)

Leave the window open. Do not restart again under normal conditions.

- Dashboard: http://127.0.0.1:8787/agent
- Model lock: `qwen3.5:4b-q4_K_M` (GTX 1650 4GB)

## Classic symptoms (still valid)

- `ModuleNotFoundError: No module named 'gems'` / `cli` → use `-Hard`
- `git pull` blocked by MERGE_HEAD → handled automatically
- PowerShell JSON breaks tool CLI → use single quotes around JSON

## Tool JSON on PowerShell

Use **single quotes** around the JSON object:

```powershell
python tools/persistent/secret_scan.py '{"text":"hello"}'
python tools/persistent/repo_map.py '{}'
```

Or key=value:

```powershell
python tools/persistent/secret_scan.py text=hello
```

## Manual nuclear (only if recover_host.ps1 itself is missing)

```powershell
cd C:\Users\Otcde\ETHER
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
git merge --abort 2>$null
git fetch origin
git reset --hard origin/main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
if (Test-Path .\.venv) { Remove-Item -Recurse -Force .\.venv }
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1
```
