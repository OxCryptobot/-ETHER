# Phase E — Mutation restore (repo-grounded regressions)

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Mutation catalog + temp fixtures from fixed solutions | **ACTIVE** |
| 2 | `batch_phase_e` direct vs bare | **ACTIVE** |
| 3 | FINDINGS update | pending data |

## Idea

Phase D used one broken snapshot per package. Phase E starts from
`fixtures/_fixed_solutions`, applies a **named mutation**, then asks tools
to restore green project tests — closer to "this regression landed, fix it".

## Host batch

```powershell
git fetch origin; git reset --hard origin/main
# .env: ETHER_PRIMARY_MODEL=qwen3.5:4b

python -m scripts.batch_phase_e --arm direct --mode scripted
python -m scripts.batch_phase_e --arm direct --mode live --max-steps 16 --timeout 500
python -m scripts.batch_phase_e --arm bare --mode live --timeout 400
```

## Non-goals

- BoN / curriculum / flywheel
- Holdout-generate redo
