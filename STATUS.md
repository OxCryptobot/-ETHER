# @ETHER Status

**Updated:** 2026-08-14T20:03Z — `core/pipeline.py` restored + terminal tool_runtime harden landed. Soft launch still BLOCKED until measured.

---

## Critical incident — CLOSED

`core/pipeline.py` was PLACEHOLDER.  
**Resolution:** full restore from last known-good content + explicit terminal harden under tool-first.

- Marker `tool_runtime_failed_terminal` is present.
- Tool-runtime non-ok / max_steps no longer falls into multi-minute generate path (closes 984s hang class).
- Commit: `a6c519a746a479bcb92a62428dc5f7303f7ed8da`

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first | COMPLETE |
| 1B AgentState | COMPLETE |
| 1C AST transactional | COMPLETE |
| 1D Measured lift | IN PROGRESS — re-measure after host pull |

## Measured (pre-incident)

- direct scripted hard: **5/5**
- pipeline live: previously 0/1 max_steps + hang — now terminal, ready for honest re-measure

## Next (host drains pending)

1. Host pulls main (or run recovery PowerShell if still stalled)
2. `p1_25` becomes a no-op / import confirmation
3. Single-fixture pipeline re-measure under the new terminal path
4. Labradorite critique on every remaining FAIL → smallest_experiment
5. Expand hard pack toward ≥10 only after green measurement
6. Keep ~10 pending for steady foreman flow

Training wheels ON. Soft launch blocked until measured lift is honest and open FAILs are closed.
