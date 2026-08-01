# Phase D — Repo-grounded eval + e2e tool path

## Context

Phase C closed with **7/7 live PASS** on synthetic fixtures (easy 2 + hard 5)
using Observe→Act→Observe tool runtime on host ≤4B.

That is necessary but not sufficient. `STATUS.md` still holds: ETHER has not
been shown to beat a bare model on honest, non-leaking tasks. TASKS.md #1 is
the next evidence-ranked move.

## Goal

1. **Measure the pipeline path** with `ETHER_TOOL_RUNTIME=1` (wire exists; live
   e2e was not measured).
2. **Repo-grounded tasks** — break real behaviour, restore via tools, judge by
   the package's own tests (no holdout leakage channel).
3. **Record** bare-generate vs tool-runtime on the same tasks.

## Non-goals

- Curriculum / bandit / flywheel re-enable
- Shell / arbitrary subprocess tools
- Optimising best-of-N selector (ceiling measured ~5.8pp)

## Slices

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Pipeline e2e under `ETHER_TOOL_RUNTIME=1` + measure script | **ACTIVE** |
| 2 | Repo-grounded task schema + mini pack (break/restore) | pending |
| 3 | Bare vs tool-runtime comparison on grounded pack | pending |
| 4 | FINDINGS / STATUS update with Phase D numbers | pending |

## Safety

- Default tool runtime **OFF**
- Staging only
- Path blocks, timeouts, max steps
- Fail closed

## Host measurement (slice 1)

```powershell
git fetch origin; git reset --hard origin/main

# Direct tool path (sanity, should match Phase C)
python -m scripts.measure_pipeline_tool --fixture ledger --path direct --live

# Pipeline path (the real Phase D slice 1 question)
python -m scripts.measure_pipeline_tool --fixture ledger --path pipeline --live --timeout 400

# Both paths on hard tier
python -m scripts.measure_pipeline_tool --tier hard --path both --live --timeout 500
```
