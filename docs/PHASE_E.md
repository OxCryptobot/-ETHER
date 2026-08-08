# Phase E — Mutation restore (repo-grounded regressions)

## Status — measured 2026-08-08 (host `qwen3.5:4b`)

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Mutation catalog + temp fixtures from fixed solutions | **CLOSED** |
| 2 | `batch_phase_e` direct vs bare | **CLOSED** |
| 3 | FINDINGS §13 | **CLOSED** |
| 4 | max-steps 24 remeasure | **CLOSED** — still 3/6 |
| 5 | ledger-only max-steps **40** | **CLOSED** — still 0/1 max_steps |

## Headline

| arm | max-steps | pass |
|-----|-----------|------|
| direct scripted | — | **6/6** |
| direct live | 16 | **3/6** |
| **direct live** | **24** | **3/6** |
| ledger only | **40** | **0/1** (max_steps, score 0.0) |
| bare live | — | **1/6** |

Raising budget 16 → 24 → **40** produced **zero additional ledger solves**.

### Direct live (max-steps 24)

| mutation | result | steps |
|----------|--------|-------|
| ledger_no_debit | FAIL max_steps (0.0) | 24 |
| ledger_double_total | FAIL max_steps (0.0) | 24 |
| topo_drop_cycle_raise | FAIL max_steps (0.571) | 24 |
| lru_no_evict | **PASS** | 16 |
| merge_drop_b_tail | **PASS** | 5 |
| intervals_no_sort | **PASS** | 5 |

### Ledger focus (max-steps 40)

| mutation | result | steps | elapsed |
|----------|--------|-------|--------|
| ledger_no_debit | FAIL max_steps (0.0) | 40 | ~611s |

(Second ledger mutation scoreboard did not land — host_agent was fail-fast on multi-step; fixed 2026-08-08 with `continue_on_fail`.)

## Reading (honest)

- **Budget is fully ruled out** for the ledger class.
- Failures are diagnosis / tool-strategy / repair-quality problems.
- Next work: tool-trace inspection + read-before-write bias + single-mutation experiments.
- Preference learning + live strategy_stats now mirror under `artifacts/` for remote observability.
- Six synthetic regressions — not a multi-repo benchmark.

## Reproduce

```powershell
python -m scripts.batch_phase_e --arm direct --mode live --max-steps 24 --timeout 900 --trace
python -m scripts.batch_phase_e --arm direct --mode live --mutation ledger_no_debit --max-steps 24 --read-first --trace
```
