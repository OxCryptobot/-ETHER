# Labradorite Critique — p1_04c_pipeline_live_hard

**Job:** p1_04c_pipeline_live_hard  
**Finished:** 2026-08-14T18:16:01Z  
**Result:** FAIL (ok=false, rc=1, moved to failed/)  
**continue_on_fail:** true  

## Taxonomy

| Field | Value |
|-------|-------|
| root_cause class | `trace_missing` / `measurement_incomplete` |
| confidence | high |
| infra? | no (code path + reporting) |
| evidence | last_job reports ok=false; scoreboard_p1_04c_live.json never appeared on origin; same pattern as p1_04 / p1_04b |

## Observed facts

- Explicit `--scoreboard artifacts/scoreboard_p1_04c_live.json` + `--mode live`
- batch_phase_d already has per-fixture + finally atomic write
- Direct arm (p1_07) produces clean scoreboards under identical host
- Pipeline arm continues to leave zero scoreboard artifact after job end
- Host heartbeat stayed live; other jobs (p1_06/07/08) PASSed around it

## Hypothesis (one only)

The pipeline live path either raises / hangs inside Pipeline().run before any scoreboard write is reached, or the host job runner terminates the process in a way that prevents the finally block from executing (or the subsequent git_push_report does not stage the new scoreboard file). Direct path is robust; pipeline path is not under the current host envelope for multi-fixture live runs.

## Smallest next experiment

Job id: `p1_12_pipeline_single_ledger`

- Reduce to **one** hard fixture (`ledger`) so the write happens after a single run
- Keep live mode + explicit scoreboard
- continue_on_fail: true (measurement)
- Timeout 600 s
- One hypothesis only: single-fixture pipeline live produces a scoreboard and lets us measure the real lift (or confirm the failure is inside Pipeline itself)

## Learning captured

- Every non-infra FAIL must produce a critique file before the next experiment
- Scoreboard absence is itself a first-class failure mode (trace_missing)
- Historical failed/ duplicates stay for history; new work uses new job ids only

## What this does not change

- Training wheels ON
- No budget bump
- No Phase 2
- One-hypothesis rule
