# Phase F — Diff-aware restore (git-style signal without external repos)

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Unified-diff in objective + `batch_phase_f` | **ACTIVE** |
| 2 | Live direct vs Phase E baseline | pending host |
| 3 | FINDINGS | pending data |

## Why

Phase E tools: **3/6**. Failures were ledger/topo max_steps. Real regression work
usually includes a **diff** (`git show` / PR). Phase F gives the agent the
unified diff of the injected mutation and measures whether that closes the gap
before wiring full `git_*` tools or external repos.

## Hypothesis

Diff-aware tools ≥ Phase E tools on the same 6 mutations (especially ledger).

## Host

```powershell
git fetch origin; git reset --hard origin/main

python -m scripts.batch_phase_f --arm direct --mode scripted
python -m scripts.batch_phase_f --arm direct --mode live --max-steps 16 --timeout 500
python -m scripts.batch_phase_f --arm bare --mode live --timeout 400
```

Baseline to beat: Phase E direct live **3/6**, bare **1/6**.

## Non-goals

- External network clones yet
- BoN / curriculum / flywheel
