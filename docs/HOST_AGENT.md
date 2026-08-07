# Host agent — zero-paste loop

## Who does what

| Actor | Action |
|-------|--------|
| **You (once)** | Start `host_agent.py` and leave it running |
| **Grok** | Pushes job JSON to `artifacts/jobs/pending/` |
| **host_agent** | Pulls, runs sprint/steps, pushes report to `artifacts/host_report_latest.*` |
| **Grok** | Reads report, implements next code, enqueues next job |

## One-time start (Windows)

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\python.exe scripts\host_agent.py
```

Keep that window open (or install as a scheduled task later).

## Job format

```json
{
  "id": "unique_id",
  "sprint": "phaseg_verify"
}
```

or explicit steps:

```json
{
  "id": "custom_1",
  "steps": [
    {"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_tool_runtime.py", "-q"]}
  ]
}
```

## Why not fully remote from chat?

Grok has GitHub write access and a Linux sandbox — not your GPU host.
The agent is the bridge. After it is running, you do not paste logs or run sprints by hand.
