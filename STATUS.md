# @ETHER Status

**Updated:** 2026-08-14T19:28Z — EMERGENCY restore of pipeline.py in progress. Soft launch BLOCKED.

---

## Critical incident

`core/pipeline.py` was briefly overwritten with PLACEHOLDER during a failed large-file push.  
**Recovery:** base64 parts + `scripts/restore_pipeline.py` + job `p1_25_restore_pipeline`.

Host must drain `p1_25` first. After restore:
- Pipeline has tool_runtime terminal harden (no multi-minute generate after max_steps)
- Direct ToolRuntime remains 5/5 proven path

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first | COMPLETE |
| 1B AgentState | COMPLETE |
| 1C AST transactional | COMPLETE |
| 1D Measured lift | IN PROGRESS — restore then re-measure |

## Measured (pre-incident)

- direct scripted hard: **5/5**
- pipeline live: 0/1 max_steps (then hung 984s) — harden addresses hang

## Next

1. Host runs p1_25 restore
2. Confirm `from core.pipeline import Pipeline` works
3. Re-run single-fixture pipeline measurement
4. Expand hard pack toward ≥10

Training wheels ON. Soft launch blocked.
