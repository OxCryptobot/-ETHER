# @ETHER Ops — how many windows?

**Answer: zero or one. Never four.**

| Mode | Windows open | How |
|------|----------------|-----|
| **Best** | **0** | Scheduled Task `ETHER-Daemon` |
| **Simple** | **1** | Foreground daemon |
| **Bad** | 3–4 | Manual flywheel + dashboard + autonomy + python |

## Clean slate (do this once now)

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main

# kill every old PS/python ETHER process
powershell -ExecutionPolicy Bypass -File .\scripts\stop_daemon.ps1
```

## Start ONE automatic process

```powershell
# Option A — background (close the window after it starts)
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1

# Option B — one visible window (easiest to debug)
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

That single Python process runs:
- flywheel (pull → test → sandbox → push)
- batch queue
- dashboard on http://127.0.0.1:8787

## Stop everything

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_daemon.ps1
```

## Do not run at the same time
- `ether flywheel --autonomous`
- `desktop_runtime.py`
- `ether dashboard`
- a second `ether_daemon.py`

Single-instance lock will abort duplicates with a clear message.
