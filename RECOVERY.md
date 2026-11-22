# Local recovery (Windows)

> **2026-11-19:** the only way to start the 1650 writer is `scripts\install_host.cmd` (once) and `scripts\host.cmd start|stop|status`. See [docs/HOST_START.md](docs/HOST_START.md). Older launchers are in `scripts/_graveyard/host_legacy/`.


## Preferred path (host agent live)

When Grok reports **stale heartbeat** or pending jobs not draining:

```powershell
cd C:\Users\Otcde\ETHER
scripts\host.cmd restart
```

Hard recovery (broken venv / `ModuleNotFoundError`):

```powershell
scripts\host.cmd setup && scripts\host.cmd restart
```

What `host.cmd restart` does: sticky stop of the ETHER-Host supervisor (graceful, then forced), then start
through the ETHER-Host task. `host.cmd setup` recreates/repairs the venv. `host.cmd status` prints the
LIVE verdict (app_alive under 6h AND ollama). No window needs to stay open.

- Status: the Grok Control Matrix (read-only) reads `artifacts/unison.json`, `supervisor.json` and `learning_summary.json` from origin; locally `scripts/ether_app.py` serves a read-only watch page on http://127.0.0.1:7843/. The old :8787 dashboard is retired (writes refused, batch 9).
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

## Manual fallback (only if scripts\host.cmd itself is missing)

```bat
cd /d C:\Users\Otcde\ETHER
git fetch origin && git merge --ff-only origin/main
.venv\Scripts\python.exe -m pip install -e .
scripts\install_host.cmd
```
