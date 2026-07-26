# @ETHER Task Board

**Updated:** 2026-07-26 — through batch 81

## Done (66–81)
| # | Item |
|---|------|
| 66–70 | Process rewards, burst-on-fail, daemon quiz |
| 71–74 | Methodology protocol, test_synth, ONBOARDING, patch_loop |
| 75 | Contextual bandit |
| 76 | Latency/burst **ledger** + Matrix data |
| 77 | expand_holdout.py |
| 78–81 | pipeline_hooks, compare_runners, scratch_multifile tier, collector ledger |

## Next stretch
| # | Task |
|---|------|
| 82 | Matrix UI cards for ledger (avg_run_ms, burst) on Intelligence tab |
| 83 | Full 40-task quiz overnight job |
| 84 | Preference pairs export for future LoRA (post 2026-08-01) |

```powershell
git fetch origin; git reset --hard origin/main
python scripts/expand_holdout.py
python scripts/wire_check.py
python -c "from core.ledger import compute_ledger; print(compute_ledger())"
pytest -q
```
