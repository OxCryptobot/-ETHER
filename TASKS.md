# @ETHER Task Board

**Updated:** 2026-07-26 — autonomy revamp

## Shipped (autonomy)
- `core/autonomy.py` recovery + auto-enqueue + baseline recovery
- Daemon: unhealthy → recovery_cycle; batch `--limit`; seed if empty
- Curriculum-only objectives (assert-nudged) in smart cycle + autonomous flywheel
- verification_score / total_tests through flywheel gates → curriculum promote
- Failures requeued to batch automatically
- AUTONOMY.md contract

## Operator
```powershell
cd C:\Users\Otcde\ETHER
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1
```

## Still polish (not blockers for stand-alone)
- File lock on batch_queue.json for concurrent drain
- Dashboard panel for batch pending/done + recovery log
- Larger fixed holdout for statistical learning curves
- Curriculum tier → `decide_burst(..., tier=...)`
