# @ETHER Status

**Updated:** 2026-08-14T18:40Z — Phase 1 close-out. 1A/1B/1C complete. 1D measurement jobs enqueued. Training wheels ON.

---

## Doctrine (locked)

- GEMS core — streamline only, never remove
- Training wheels ON until measured lift on expanded repo-oracle
- One hypothesis per job; Labradorite mandatory on non-infra FAIL
- Tool-first is the required direction
- LoRA dual-flag gated; dry-run default only
- **Every FAIL → critique + lesson + smallest experiment** (never blind re-run of the same failed file)

---

## Phase 1 board — CLOSEOUT

| Package | Status |
|---------|--------|
| 1A Tool-first default | **COMPLETE** |
| 1B AgentState durable | **COMPLETE** (wired + durable) |
| 1C AST transactional edits | **COMPLETE** (p1_06 PASS + AST-gate live) |
| 1D Expand eval + measured lift | **IN PROGRESS — final measurement batch** |

**Gate to Phase 2 (exact):**
1. Pipeline scoreboard lands on hard pack (p1_12 → p1_17/p1_18)
2. Pipeline ≥ direct on the measured fixtures (or honest delta recorded)
3. Hard pack expanded toward ≥10 (currently 5 hard fixtures)
4. Evolution FAILs closed via Labradorite path
5. train_gates + preference health green

---

## What is already proven

- Direct / tool-runtime hard pack: **5/5** (p1_07, p1_11, phase_d)
- EditTransaction + write-time AST gate: verified green
- AgentState durable across gems
- Resilient scoreboard harness (per-fixture + finally + atomic)
- Fail → Labradorite critique → new job id only (lesson 023)

## Current measurement path (one hyp at a time)

1. `p1_12_pipeline_single_ledger` — single fixture live (smallest experiment after p1_04c)
2. `p1_17_pipeline_hard_scripted` — full hard pack pipeline scripted (scoreboard reliability)
3. `p1_18_pipeline_hard_live` — full hard pack pipeline live
4. `p1_19_direct_vs_pipeline_compare` — side-by-side lift matrix
5. `p1_20_train_gates_final` — doctrine green

Host is live. It drains FIFO. Steady pending depth maintained.

## Remaining for full Phase 1 green

- Scoreboard must appear for pipeline (p1_12 is the gate for that)
- Expand hard fixtures from 5 → ≥10 (next concrete work after measurement lands)
- Confirm no open non-infra evolution FAILs

Do not lift training wheels. Do not start Phase 2 until the gate numbers are on origin.

## Next action only

Host drains p1_12 → read `artifacts/scoreboard_p1_12_ledger.json` → if present and usable, proceed to p1_17. If still missing, Labradorite on the single-fixture path only.
