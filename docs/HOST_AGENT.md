# Host agent — zero-paste loop

## Who does what

| Actor | Action |
|-------|--------|
| **You (once)** | Run recovery or start launcher; leave the window open |
| **Grok** | Pushes job JSON to `artifacts/jobs/pending/` |
| **ether_host** | Dashboard + host_agent + foreman in one process |
| **Grok** | Reads reports from GitHub; never asks you to paste logs |

## Start / recover (Windows)

**Normal start** (already on latest main):

```powershell
cd C:\Users\Otcde\ETHER
powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1
```

**Recovery** (stale heartbeat, pending not draining, or after a long idle):

```powershell
cd C:\Users\Otcde\ETHER
powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1
```

`recover_host.ps1` kills stale host python processes, `git fetch` + `reset --hard origin/main`, then enters the self-healing launcher loop.

### Launcher exit contract (`start_ether_host.ps1`)

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 0 | Clean stop (Ctrl+C) | Exit permanently |
| 42 | Source updated on origin | Restart in 1s |
| other | Crash | Restart with exponential backoff (3s → 30s max) |

Do **not** ask the user to restart again under normal conditions. One recovery is enough; the launcher keeps the host alive.

- Dashboard: `http://127.0.0.1:8787/agent`
- Model lock: `ETHER_PRIMARY_MODEL=qwen3.5:4b-q4_K_M` (host ≤4B)

## Job format

Prefer direct argv:

```json
{
  "id": "unique_id",
  "note": "short purpose",
  "class": "fast",
  "continue_on_fail": false,
  "steps": [
    {
      "argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_tool_runtime.py", "-q", "--tb=line"],
      "timeout": 180
    }
  ]
}
```

## Observability (Grok reads these — never ask the user)

- `artifacts/host_agent_status.json` — heartbeat, phase, last_job
- `artifacts/host_agent_last_job.json` — last result
- `artifacts/jobs/{pending,done,failed}/`
- `artifacts/performance_benchmark.json`
- scoreboards / preference_summary / strategy_stats

## Why not fully remote from chat?

Grok has GitHub write access and a Linux sandbox — not your GPU host.
The agent is the bridge. After it is running, you do not paste logs or run sprints by hand.
