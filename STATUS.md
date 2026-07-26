# @ETHER Status

**Autonomy mode is the product.** Daemon stands alone.

## Start (one command)

```powershell
cd C:\Users\Otcde\ETHER
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1
```

Reads: [AUTONOMY.md](AUTONOMY.md)

## What changed (2026-07-26 autonomy revamp)

- `core/autonomy.py` — recovery_cycle, auto-enqueue failures, guardian baseline recovery
- Daemon runs recovery when unhealthy (cooldown), drains batch with limit, seeds queue
- Smart cycle / flywheel: curriculum-only objectives, verification metrics, failure → batch
- Assert nudge on all autonomous objectives

## Health / tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\health_check.py --skip-sandbox
```

`intel_gates` red means guardian freeze or stale bench/quiz — recovery_cycle is designed to clear this without you.
