# @ETHER Autonomy Contract

**Goal:** leave the machine running; the system improves without chat babysitting.

## One human action

```powershell
cd C:\Users\Otcde\ETHER
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1
```

Optional background:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Background
```

That is the product entrypoint. Dashboard: http://127.0.0.1:8787

## What runs without you

| Loop | Interval (default) | Behavior |
|------|--------------------|----------|
| Flywheel / smart cycle | 900s | Curriculum objective → verify → promote/demote → push report |
| Batch drain | 600s | Process up to `ETHER_BATCH_LIMIT` (2) pending jobs |
| Recovery | on unhealthy + cooldown 1800s | bench --fast → quiz → scoreboard → baseline/guardian re-eval |
| Bench discipline | every 4 cycles | fast bench + guardian re-eval |
| Quiz discipline | every 6 cycles | holdout sample + SCOREBOARD.md |
| Tool reconcile | every 3 cycles | promote safe quarantine tools |

## Closed loops

1. **Curriculum** samples failure-driven + tier tasks (assert-nudged).
2. **Pipeline** records `verification_score` + `total_tests` into experience.
3. **after_agentic** updates curriculum (verified wins only) and **auto-enqueues failures** into batch.
4. **Guardian** freezes fabricate on regression; **recovery** can advance baseline when metrics recover (`ETHER_GUARDIAN_AUTO_BASELINE=1`).
5. **Daemon** refuses to stay silent on `NOT HEALTHY` — it runs `core.autonomy.recovery_cycle`.

## Env knobs (defaults are autonomy-on)

```
ETHER_CURRICULUM=1
ETHER_AUTO_ENQUEUE=1
ETHER_GUARDIAN_AUTO_BASELINE=1
ETHER_DAEMON_FLYWHEEL=1
ETHER_DAEMON_BATCH=1
ETHER_DAEMON_DASHBOARD=1
ETHER_BATCH_LIMIT=2
ETHER_DAEMON_INTERVAL=900
ETHER_BATCH_INTERVAL=600
ETHER_RECOVERY_COOLDOWN_S=1800
```

## Proof overnight

Morning checks (no rebuild required):

```powershell
Get-Content memory\daemon\heartbeat.txt
Get-Content memory\daemon\healthy.json
Get-Content memory\flywheel\latest.json | Select-Object -First 40
.\.venv\Scripts\python.exe -m cli.main batch status
.\.venv\Scripts\python.exe .\scripts\health_check.py --skip-sandbox
```

Expect: fresh heartbeat, flywheel history growth, batch done entries, scoreboard timestamps moving.

## Non-goals

- Cloud multi-agent swarms
- Replacing Ollama with a hosted API by default
- Human-in-the-loop for every cycle
