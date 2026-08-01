# Phase D — Repo-grounded eval + e2e tool path

## Status — CLOSED 2026-08-01

| Slice | Content | Status |
|-------|---------|--------|
| 1 | Pipeline e2e under `ETHER_TOOL_RUNTIME=1` | **CLOSED** |
| 2 | Task pack (`fixtures/phase_d_tasks.json`) | **CLOSED** |
| 3 | Bare vs direct vs pipeline batch | **CLOSED** |
| 4 | FINDINGS / STATUS numbers | **CLOSED** |

## Headline (host `qwen3.5:4b`)

| arm | hard pack (5) |
|-----|----------------|
| direct | **5/5** |
| pipeline (`--max-steps 16`) | **5/5** |
| bare | **0/5** |

Ledger/topo need `max_steps≥16` on 4B; 12 steps under 3b default was a false negative.

## Reproduce

```powershell
git fetch origin; git reset --hard origin/main
# .env: ETHER_PRIMARY_MODEL=qwen3.5:4b  (must match `ollama list`)

python -m scripts.batch_phase_d --arm direct --mode scripted --tier hard
python -m scripts.batch_phase_d --arm pipeline --mode live --tier hard --max-steps 16 --timeout 500
python -m scripts.batch_phase_d --arm bare --mode live --tier hard --timeout 400
```

Scoreboard: `artifacts/scoreboard_phase_d.json`

## Non-goals (still)

- Curriculum / bandit / flywheel re-enable without new evidence
- Shell tools
- Best-of-N revival
- Claiming holdout-generate win (ablation still says no)
