# @ETHER Status

**Updated:** 2026-08-14T18:35Z — Failed jobs converted into learning. Steady 10-job pending flow enabled. Training wheels ON.

---

## Doctrine (locked)

- GEMS core — streamline only, never remove
- Training wheels ON until measured lift on expanded repo-oracle
- One hypothesis per job; Labradorite mandatory on non-infra FAIL
- Tool-first is the required direction
- LoRA dual-flag gated; dry-run default only
- **Every FAIL → critique + lesson + smallest experiment** (never blind re-run of the same failed file)

---

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first default | **LANDED** |
| 1B AgentState durable | **WIRED** |
| 1C AST transactional edits | **LANDED + VERIFIED** (p1_06 PASS) |
| 1D Expand eval + close FAILs | **IN PROGRESS** — pipeline measurement still open; FAILs now feed learning |

**Gate to Phase 2:** measured pipeline lift on ≥10 hard tasks + evolution FAILs closed.

---

## Learning from failed queue

| Failed job | Learning action |
|------------|-----------------|
| p1_04 / p1_04b / p1_04c | Labradorite critiques written; root_cause = `trace_missing` |
| Historical phase_e / phaseg / flywheel | Left in failed/ for history; do not re-process blindly |
| New rule | lesson **023_fail_to_learning** — every non-infra FAIL becomes structured critique + new job id only |

Smallest experiment now in queue: `p1_12_pipeline_single_ledger` (one fixture, live, explicit scoreboard).

---

## Steady pending flow (BATCH_SIZE=10)

Foreman now fills up to 10 sequential curriculum / learning jobs when idle. Current pending (FIFO):

1. lab_crit_p1_04c
2. p1_12_pipeline_single_ledger
3. p1_09_train_gates_reverify
4. p1_10_ast_gate_reverify
5. p1_11_direct_hard_rebaseline
6. p1_13_tool_runtime_smoke
7. p1_14_repo_oracle_gate
8. p1_15_preference_summary
9. p1_16_evolution_smoke
10. (foreman will keep topping up from curriculum)

Host is live (heartbeat recent). It will drain FIFO back-to-back.

---

## What works

- Tool-runtime / direct hard pack **5/5**
- EditTransaction + AST-gate (p1_06 green)
- AgentState durable
- Resilient scoreboard harness (per-fixture + finally + atomic)
- Fail → learning pipeline now explicit

## Next action only

1. Host drains the 10-job batch
2. Read scoreboard_p1_12_ledger.json (or critique from lab_crit)
3. If scoreboard lands and lift visible → expand toward ≥10 hard
4. If still missing → next single hyp only (Labradorite again)

Do not lift training wheels. Do not start Phase 2.
