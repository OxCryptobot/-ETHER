# HOST RESTART REQUIRED

## What is true
- All critical fixes + moonshots **are on `origin/main`**
- Host process is **alive** (heartbeat ok)
- Host is still running **OLD code in memory**

## Proof
Recent jobs still include `ss_kill_live_pending` — that template was **removed** from `scripts/foreman.py` on disk.
Python does not reload `scripts.foreman` / `scripts.host_agent` after `git pull`.

## What you must do (Windows)
1. Stop the host agent window / process (Ctrl+C or close the terminal running it)
2. From `C:\\Users\\Otcde\\ETHER`:

```powershell
git fetch origin
git reset --hard origin/main
.venv\Scripts\python.exe -m scripts.host_agent
```

Or use your usual `start_ether_host.ps1` **after** the reset.

## After restart you should see
- No more `ss_kill_live_pending` jobs
- Jobs like `ss_measure_tick_*`
- Commits: `host measure_tick: moonshot panels`
- Files: `artifacts/smoothness.json`, `honest_kpi.json`, `latency_slo.json`
- Job `p3_7_moonshots` run once

Until restart: **zero new behavior will apply**, no matter how long the host stays up.
