# Phase E — Mutation restore (repo-grounded regressions)

## Status — measured 2026-08-08 (host `qwen3.5:4b`)

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Mutation catalog + temp fixtures from fixed solutions | **CLOSED** |
| 2 | `batch_phase_e` direct vs bare | **CLOSED** |
| 3 | FINDINGS §13 | **CLOSED** |
| 4 | max-steps 24 remeasure | **CLOSED** — still 3/6 |

## Headline

| arm | max-steps | pass/6 |
|-----|-----------|--------|
| direct scripted | — | **6/6** |
| direct live | 16 | **3/6** |
| **direct live** | **24** | **3/6** |
| bare live | — | **1/6** |

Raising budget 16 → 24 produced **zero additional solves**.

### Direct live (max-steps 24)

| mutation | result | steps |
|----------|--------|-------|
| ledger_no_debit | FAIL max_steps (0.0) | 24 |
| ledger_double_total | FAIL max_steps (0.0) | 24 |
| topo_drop_cycle_raise | FAIL max_steps (0.571) | 24 |
| lru_no_evict | **PASS** | 16 |
| merge_drop_b_tail | **PASS** | 5 |
| intervals_no_sort | **PASS** | 5 |

### Bare live (prior)

| mutation | result |
|----------|--------|
| ledger_no_debit | FAIL (0.86) |
| ledger_double_total | FAIL (0.0) |
| topo_drop_cycle_raise | **PASS** |
| lru_no_evict | FAIL (0.3) |
| merge_drop_b_tail | FAIL (0.5) |
| intervals_no_sort | FAIL (0.2) |

## Reading

- Mutation-restore is **harder** than Phase D fixtures (tools 5/5 → 3/6).
- Tools still beat bare (**3/6 vs 1/6**).
- **Budget is not the bottleneck** for ledger/topo — they exhaust 24 steps without solving.
- Next work targets diagnosis quality / tool strategy on the hard class (see `docs/FINDINGS_PHASE_E_STEPS24.md`).
- Six synthetic regressions — not a multi-repo benchmark.

## Reproduce

```powershell
python -m scripts.batch_phase_e --arm direct --mode live --max-steps 24 --timeout 900
python -m scripts.batch_phase_e --arm bare --mode live --timeout 400
```
