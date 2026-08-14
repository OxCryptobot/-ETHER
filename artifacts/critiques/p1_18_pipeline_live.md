# Labradorite Critique — p1_18_pipeline_live

**Job:** p1_18_pipeline_hard_live  
**Finished:** ~2026-08-14T19:10Z  
**Result:** partial scoreboard landed (sentinel harness worked)  
**continue_on_fail:** true  

## Taxonomy

| Field | Value |
|-------|-------|
| root_cause class | `budget_exhaust` + `repair_quality` |
| confidence | high |
| infra? | no |
| evidence | scoreboard_p1_18_pipeline_live.json: lru pipeline live → tool_runtime steps=16 score=0.000 reason=max_steps; then code stage timed out; elapsed 984s for one fixture |

## Observed facts

- Scoreboards now land (sentinel-on-entry + host recovery fixed `trace_missing`).
- Direct scripted hard pack remains **5/5** (~2s/fixture).
- Pipeline live on 4B: tool_runtime hits max_steps without passing tests, then Pipeline falls into a long Rose Quartz generate path that times out.
- Control-flow bug: when `tr.ok` is False, Pipeline still enters the `while attempt` generation loop and burns wall-clock.

## Hypothesis (one only)

Under tool-first doctrine, a completed tool_runtime attempt (pass or fail) must be terminal. Falling into generate after max_steps is both slow and net-negative on this hardware. The 4B model does not reliably complete the hard pack within 16 live tool steps; the correct product path is pure ToolRuntime (direct), not Pipeline-wrapped generate fallback.

## Smallest next experiment / fix

1. **Code harden (this commit):** In Pipeline, if tool_runtime ran and returned non-ok, set `_tool_path_complete = True` and terminate with the tool_runtime result. Do not enter the generate loop.
2. Measurement continues on direct (proven 5/5) for Phase 1 gate.
3. Live tool_runtime quality is a separate (later) hypothesis once the hang is gone.

## Learning

- Scoreboard landing is fixed.
- Pipeline live hang was control-flow, not missing scoreboard.
- Direct ToolRuntime remains the best-in-class path on ≤4B hardware.
