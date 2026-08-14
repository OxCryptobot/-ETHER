# Labradorite Critique — p1_04_measure_pipeline_lift

**Job:** p1_04_measure_pipeline_lift  
**Finished:** 2026-08-08T22:25:26Z  
**rc:** 1  
**continue_on_fail:** true (measurement job)  
**Host state after:** dead (no further ticks)

## Taxonomy (mandatory)

| Field | Value |
|-------|-------|
| root_cause class | `measurement_incomplete` / possible `budget_exhaust` or `repair_quality` on hard fixtures |
| confidence | medium (no scoreboard artifact landed for this exact run) |
| infra? | no — pure measurement under training wheels |
| smallest_experiment | Re-run the same arm with explicit scoreboard path + per-fixture timeout logging |

## Observed facts

- Command: `python -m scripts.batch_phase_d --arm pipeline --mode scripted --tier hard`
- Timeout allotted: 600 s
- Hard fixtures: lru, merge, ledger, topo, intervals
- Prior Phase D hard pack under tool-runtime was 5/5 (direct) and 5/5 (pipeline)
- No `artifacts/scoreboard_phase_d.json` (or variant) was pushed for this run
- Host heartbeat stopped immediately after the FAIL report

## Hypothesis (one only)

The pipeline arm under scripted mode exhausted its per-fixture step or wall-clock budget on one of the harder fixtures (most likely ledger / topo / intervals), causing the overall batch to return non-zero. Because the scoreboard write happens at the end of `main()`, a mid-run timeout or unhandled exception can leave zero measurement artifacts.

## Smallest next experiment

Job id: `p1_04b_measure_pipeline_lift_verbose`

- Same arm + mode + tier
- Add `--timeout 480` (slightly tighter per fixture) and force scoreboard path
- Capture stdout/stderr into the job result so we never again lose the matrix
- Still `continue_on_fail: true`

## What this does **not** change

- Training wheels stay ON
- No generation-first reversion
- No new model
- No Phase 2 work
