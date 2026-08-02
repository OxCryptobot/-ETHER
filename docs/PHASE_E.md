# Phase E — Mutation restore (repo-grounded regressions)

## Status — measured 2026-08-01 (host `qwen3.5:4b`)

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Mutation catalog + temp fixtures from fixed solutions | **CLOSED** |
| 2 | `batch_phase_e` direct vs bare | **CLOSED** |
| 3 | FINDINGS §13 | **CLOSED** |

## Headline

| arm | pass/6 mutations |
|-----|------------------|
| direct scripted | **6/6** |
| **direct live** | **3/6** |
| **bare live** | **1/6** |

### Direct live

| mutation | result |
|----------|--------|
| ledger_no_debit | FAIL max_steps (0.0) |
| ledger_double_total | FAIL max_steps (0.0) |
| topo_drop_cycle_raise | FAIL max_steps (0.571) |
| lru_no_evict | **PASS** |
| merge_drop_b_tail | **PASS** |
| intervals_no_sort | **PASS** |

### Bare live

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
- Ledger burns 16-step budget; topo mixed (bare one lucky pass).
- Six synthetic regressions — not a multi-repo benchmark.

## Reproduce

```powershell
python -m scripts.batch_phase_e --arm direct --mode live --max-steps 16 --timeout 500
python -m scripts.batch_phase_e --arm bare --mode live --timeout 400
```
