# Labradorite Critique — p1_04b_measure_pipeline_lift_verbose

**Job:** p1_04b_measure_pipeline_lift_verbose  
**Finished:** ~2026-08-14T17:30Z  
**Result:** FAIL (job file in failed/, no scoreboard_p1_04b.json landed)  
**continue_on_fail:** true  

## Taxonomy

| Field | Value |
|-------|-------|
| root_cause class | `measurement_incomplete` / `trace_missing` |
| confidence | high |
| infra? | no |
| evidence | scoreboard path was explicitly requested; file absent on origin after job; job moved to failed/ |

## Observed facts

- Explicit `--scoreboard artifacts/scoreboard_p1_04b.json`
- Mode = scripted, arm = pipeline, tier = hard
- Direct arm (p1_07) under identical conditions produced clean 5/5 scoreboard and PASS
- Historical Phase D pipeline was 5/5 (prior run)
- batch_phase_d writes the scoreboard only at the end of main(); any unhandled exception or job-runner kill before the write leaves zero artifact
- Host continued to drain p1_06 / p1_07 / p1_08 successfully after the FAIL

## Hypothesis (one only)

The pipeline + scripted path inside `Pipeline().run` is either raising after partial work or the host job runner is terminating the process (timeout / signal) before the final scoreboard write. Direct arm is robust; pipeline arm is not under the current host job envelope for scripted mode.

## Smallest next experiment

Job id: `p1_04c_pipeline_live_hard`

- Switch to `--mode live` (matches the original successful Phase D measurement conditions more closely)
- Keep explicit scoreboard path
- Raise job timeout to 1200 s
- Still measurement → `continue_on_fail: true`
- One hypothesis only: live mode produces the scoreboard and confirms (or falsifies) the 5/5 pipeline lift

## What this does not change

- Training wheels ON
- No budget bump on tool steps
- No Phase 2
- No generation-first
- AST gate and 1C remain untouched
