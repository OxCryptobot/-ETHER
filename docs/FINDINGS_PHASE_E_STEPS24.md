# FINDINGS — Phase E live max-steps 24 (2026-08-08)

## Headline

| arm | max-steps | pass/6 |
|-----|-----------|--------|
| direct live | 16 (prior) | 3/6 |
| **direct live** | **24** | **3/6** |

Raising the step budget from 16 → 24 produced **zero additional solves**.

## Per-mutation (direct live, steps=24)

| mutation | ok | score | n_steps | reason |
|----------|----|-------|---------|--------|
| ledger_no_debit | FAIL | 0.0 | 24 | max_steps |
| ledger_double_total | FAIL | 0.0 | 24 | max_steps |
| topo_drop_cycle_raise | FAIL | 0.571 | 24 | max_steps |
| lru_no_evict | PASS | 1.0 | 16 | tests passed |
| merge_drop_b_tail | PASS | 1.0 | 5 | tests passed |
| intervals_no_sort | PASS | 1.0 | 5 | tests passed |

## Reading

- Ledger and topo are **not** simple budget problems.
- The agent exhausts the step allowance without restoring correct behaviour.
- The three easier mutations still solve cleanly and often in far fewer than 24 steps.
- Next experiments must target **search / diagnosis quality** or **tool-use strategy** on the hard class, not blanket step inflation.

## Next measured moves (ordered)

1. Record preferences from this scoreboard → live strategy stats (done via job).
2. Inspect tool traces on ledger failures (what tools were called, did it ever read the mutated file correctly?).
3. Focused experiment: higher steps **only** on ledger + stronger “read before write” bias, or a repair-specific decide prompt.
4. Only after evidence, consider architecture changes to ToolRuntime for hard regressions.
