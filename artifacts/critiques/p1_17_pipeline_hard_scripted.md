# Labradorite Critique — p1_17_pipeline_hard_scripted

**Job:** p1_17_pipeline_hard_scripted  
**Finished:** 2026-08-14T18:53:09Z  
**Result:** FAIL (ok=false, rc=1)  
**continue_on_fail:** true  

## Taxonomy

| Field | Value |
|-------|-------|
| root_cause class | `trace_missing` / `measurement_incomplete` |
| confidence | high |
| infra? | no |
| evidence | last_job ok=false; no scoreboard_p1_17_pipeline_scripted.json on origin; same pattern as p1_04 / p1_04b / p1_04c / p1_12 |

## Observed facts

- Direct arm consistently produces scoreboards (p1_07, p1_11, phase_d) under identical host and batch_phase_d harness.
- Pipeline arm (scripted or live) continues to leave zero scoreboard artifact after job end, even after the 2026-08-14 per-fixture + finally atomic write.
- Host heartbeat stayed live; other jobs (direct, AST, train_gates) PASS around it.
- Job timeout was 900 s — sufficient for 5 fixtures.

## Hypothesis (one only)

Either:
1. An exception or early exit occurs before the first incremental `_write_scoreboard` (or during Pipeline import / first fixture) and the finally block is not reached under the host job runner envelope, **or**
2. The scoreboard is written locally but `git_push_report` does not stage the new `scoreboard_p1_17_*.json` path.

Direct path is robust. Pipeline path is not under the current host envelope for multi-fixture (and previously single-fixture) runs.

## Smallest next experiment

Job id: `p1_21_pipeline_ledger_sentinel`

- Single fixture (`ledger`)
- Pipeline arm, scripted mode
- Explicit scoreboard path
- **Harness hardened**: sentinel scoreboard written on entry (before any work)
- continue_on_fail: true
- One hypothesis only: with sentinel-on-entry, a scoreboard artifact *must* appear on origin. If it does, we can read real pipeline numbers. If it still does not, the bug is in host git_push_report path selection, not in batch_phase_d.

## Learning captured

- Scoreboard absence is a first-class failure mode (`trace_missing`).
- Sentinel-on-entry is the correct hardening for measurement jobs under an external job runner.
- Soft launch remains blocked until pipeline scoreboard lands and lift is measured.

## What this does not change

- Training wheels ON
- No budget bump
- No Phase 2
- One-hypothesis rule
