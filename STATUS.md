# @ETHER Status

**Updated:** 2026-08-14T19:00Z — Pipeline measurement still blocked (trace_missing). Harness hardened with sentinel scoreboard. Soft launch BLOCKED.

---

## Doctrine (locked)

- GEMS core — streamline only, never remove
- Training wheels ON until measured lift on expanded repo-oracle
- One hypothesis per job; Labradorite mandatory on non-infra FAIL
- Tool-first is the required direction
- LoRA dual-flag gated; dry-run default only
- **Every FAIL → critique + lesson + smallest experiment** (never blind re-run of the same failed file)
- **Soft launch is blocked until pipeline scoreboard lands and Phase 1 gate is green**

---

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first default | **COMPLETE** |
| 1B AgentState durable | **COMPLETE** |
| 1C AST transactional edits | **COMPLETE** |
| 1D Expand eval + measured lift | **BLOCKED on pipeline scoreboard** |

**Gate to Phase 2 / soft launch:**
1. Pipeline scoreboard must appear on origin (p1_21 sentinel is the next test)
2. Pipeline numbers measured on hard pack
3. Honest delta vs direct recorded
4. Hard pack expanded toward ≥10
5. train_gates + preference health green

---

## Current problem (must resolve)

`p1_17_pipeline_hard_scripted` → ok=false, **no scoreboard on origin**.  
Same class as p1_04 / p1_04b / p1_04c / p1_12.  
Direct arm is solid (5/5). Pipeline arm reporting is not.

**Fix applied this turn:** `batch_phase_d.py` now writes a **sentinel scoreboard on entry** (before any fixture work). This guarantees an artifact exists even if Pipeline import or first fixture raises.

## Next measurement path (one hyp)

1. `p1_21_pipeline_ledger_sentinel` — single ledger + sentinel harness
2. If scoreboard lands → `p1_22` full hard pack pipeline scripted
3. `p1_23` direct rebaseline (control)
4. `p1_24` doctrine final

Host is live. Pending topped up. Training wheels ON. Soft launch remains blocked.

## Next action only

Host drains `p1_21`. Read `artifacts/scoreboard_p1_21_ledger_sentinel.json`.  
If present → proceed. If still missing → root cause is host git_push_report path selection, not the measurement script.
