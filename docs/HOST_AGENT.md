# Host agent — zero-paste loop

> **2026-11-19:** the only way to start the 1650 writer is `scripts\install_host.cmd` (once) and `scripts\host.cmd start|stop|status`. See [docs/HOST_START.md](HOST_START.md). Older launchers are in `scripts/_graveyard/host_legacy/`.


## Who does what

| Actor | Action |
|-------|--------|
| **You (once)** | Run `scripts\install_host.cmd`; no window to keep open |
| **Grok** | Pushes job JSON to `artifacts/jobs/pending/` |
| **ETHER-Host** | Task -> `host_supervisor.py` -> `host_main.tick` (the only writer) |
| **Grok** | Reads reports from GitHub; never asks you to paste logs |

## Start / recover (Windows)

**Normal start** (already on latest main):

```powershell
cd C:\Users\Otcde\ETHER
scripts\host.cmd start
```

**Recovery** (stale heartbeat, pending not draining, live spam, or after a long idle):

```powershell
cd C:\Users\Otcde\ETHER
scripts\host.cmd restart
# broken venv / ModuleNotFound → add -Hard
scripts\host.cmd setup && scripts\host.cmd restart
```

`host.cmd restart` = sticky stop (waits for the current pass, then forces) + start via the ETHER-Host task.
`host.cmd setup` rebuilds the venv. No hard reset: host_main's `sync_writer` rebases and keeps unpublished kept edits.

### Supervisor contract (`scripts/host_supervisor.py`)

| Event | Action |
|-------|--------|
| Each cycle | stale `.git/index.lock` repair -> `git pull --ff-only` -> ensure `ollama serve` -> one `python -m scripts.host_main` pass (timeout 30 min) |
| Pass crashed / timed out | exponential backoff 15s -> 900s max; reset on next success |
| Pull changed the supervisor itself | release lock, start a fresh copy, exit |
| `host.cmd stop` | sticky `artifacts/host.stop`; the 5-min ensure trigger will not undo it |
| Process died | Task Scheduler: restart-on-failure + 5-min ensure trigger; OS lock means never two copies |

- Status: the Grok Control Matrix (read-only) reads `artifacts/unison.json`, `supervisor.json` and `learning_summary.json` from origin; locally `scripts/ether_app.py` serves a read-only watch page on http://127.0.0.1:7843/. The old :8787 dashboard is retired (writes refused, batch 9).
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
