# @ETHER Task Board

**Updated:** 2026-07-26 — continuous autonomy build

## Shipped
- Autonomy core: recovery, auto-enqueue, guardian baseline recovery
- Daemon stand-alone: recovery on unhealthy, batch drain, seed
- Curriculum-only objectives + assert nudge
- verification_score through flywheel gates
- Batch queue exclusive lock + claim/commit under lock
- decide_burst reads curriculum tier automatically
- Dashboard snapshot includes batch + autonomy events (v0.4.4)

## Remaining polish
- Larger fixed holdout curves for statistical learning
- UI strip rendering for batch pending in index.html (API already ships data)
- Optional Windows scheduled-task verify path from CI
