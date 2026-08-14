# @ETHER Status

**Updated:** 2026-08-14T17:56Z — Host recovered and drained Phase 1 batch. Direct hard 5/5 confirmed. Pipeline measurement still incomplete (p1_04b no scoreboard). Next hyp enqueued under Labradorite. Training wheels ON.

---

## Doctrine (locked)

- GEMS core — streamline only, never remove
- Training wheels ON until measured lift on expanded repo-oracle
- One hypothesis per job; Labradorite mandatory on non-infra FAIL
- Tool-first is the required direction
- LoRA dual-flag gated; dry-run default only

---

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first default | **LANDED** |
| 1B AgentState durable | **WIRED** |
| 1C AST transactional edits | **LANDED + VERIFIED** (p1_06 PASS) |
| 1D Expand eval + close FAILs | **IN PROGRESS** — pipeline scoreboard still missing |

**Gate to Phase 2:** measured pipeline lift on ≥10 hard tasks + evolution FAILs closed.

---

## Latest results (host drain)

| Job | Result |
|-----|--------|
| p1_04b_measure_pipeline_lift_verbose | **FAIL** (no scoreboard landed) → Labradorite critique written |
| p1_06_ast_transaction_tests | **PASS** |
| p1_07_measure_direct_hard | **PASS** — 5/5 hard (direct, scripted) |
| p1_08_expand_hard_count | **PASS** |

Direct baseline is solid. Pipeline lift measurement is the open item.

---

## Pending (FIFO)

1. `p1_04c_pipeline_live_hard` — pipeline live + scoreboard (single hyp after critique)

---

## What works

- Tool-runtime / direct hard pack **5/5** (re-confirmed 2026-08-14)
- EditTransaction + AST-gate on write_file (p1_06 green)
- AgentState durable
- Host agent recovery + FIFO drain
- Foreman sequential under wheels

## Next action only

1. Host drains p1_04c (already pending)
2. Read scoreboard_p1_04c_live.json
3. If PASS with lift → expand hard count toward ≥10
4. If FAIL → Labradorite again, one hyp only

Do not lift training wheels. Do not start Phase 2.
