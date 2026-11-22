# @ETHER Local Daemon (24/7 autonomy)

> **2026-11-19:** the only way to start the 1650 writer is `scripts\install_host.cmd` (once) and `scripts\host.cmd start|stop|status`. See [docs/HOST_START.md](docs/HOST_START.md). Older launchers are in `scripts/_graveyard/host_legacy/`.


## Honest boundary

| Layer | Can run without you / chat |
|-------|----------------------------|
| Cloud chat (Grok) | **No** — sessions go idle; cannot push code 24/7 |
| Windows daemon on your PC | **Yes** — flywheel + batch queue + optional dashboard |
| GitHub repo | Passive/receives commits from **your** daemon |

**100% autonomous activity** means: a process on *your* machine, not this chat staying awake.

## Install (once)

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
scripts\install_host.cmd
schtasks /Run /TN ETHER-Daemon
```

## What it does

1. **Flywheel** every `ETHER_DAEMON_INTERVAL` (default 900s): pull, test, agentic sandbox, gated push  
2. **Batch worker** every `ETHER_BATCH_INTERVAL` (default 1800s): next item in `memory/batch_queue.json`  
3. ~~Dashboard~~ retired (batch 9). Status: the Grok Control Matrix (read-only) reads `artifacts/unison.json`, `supervisor.json` and `learning_summary.json` from origin; locally `scripts/ether_app.py` serves a read-only watch page on http://127.0.0.1:7843/. The old :8787 dashboard is retired (writes refused, batch 9).  

## Control

```powershell
schtasks /Run /TN ETHER-Daemon
schtasks /End /TN ETHER-Daemon
schtasks /Delete /TN ETHER-Daemon /F
Get-Content C:\Users\Otcde\ETHER\memory\daemon\heartbeat.txt
Get-Content C:\Users\Otcde\ETHER\memory\daemon\daemon.log -Tail 40
```

## Manual (foreground)

```powershell
cd C:\Users\Otcde\ETHER
.\.venv\Scripts\python.exe .\scripts\ether_daemon.py
```

## Queue more work without the chat

Edit `memory/batch_queue.json` → add to `pending`:

```json
{
  "id": 99,
  "kind": "pipeline",
  "title": "my task",
  "objective": "Write only Python: print(1+1)"
}
```

Or:

```json
{
  "id": 100,
  "kind": "command",
  "title": "bench",
  "command": ["python", "scripts/bench.py"]
}
```

Daemon picks them up on the next batch tick.

## Env knobs

| Var | Default | Meaning |
|-----|---------|---------|
| ETHER_DAEMON_INTERVAL | 900 | Flywheel seconds |
| ETHER_BATCH_INTERVAL | 1800 | Batch worker seconds |
| ETHER_DAEMON_FLYWHEEL | 1 | Enable flywheel |
| ETHER_DAEMON_BATCH | 1 | Enable batch queue |
| ETHER_DAEMON_DASHBOARD | 1 | Enable Matrix UI |
