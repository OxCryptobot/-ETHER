# @ETHER Task Board

**Updated:** 2026-07-26 — through batch 81

## Done (66–81)
| # | Item |
|---|------|
| 66–70 | Process rewards, burst-on-fail, daemon quiz |
| 71 | Side-by-side protocol |
| 72 | test_synth |
| 73 | ONBOARDING.md |
| 74 | patch_loop (scratch only) |
| 75 | Contextual bandit |
| 76 | Ledger + Matrix fields (avg_run_ms, burst calls) |
| 77 | expand_holdout.py |
| 78–81 | prep hooks in Clear Quartz; bandit auto-tier; compare_run.py; scratch curriculum |

## Next
| # | Task |
|---|------|
| 82 | Dashboard UI cards for ledger stage_avg_ms |
| 83 | Full 40-task quiz weekly job |
| 84 | Human compare fill-in for Aider/Continue columns |

```powershell
git fetch origin; git reset --hard origin/main
python scripts/expand_holdout.py
python scripts/compare_run.py --limit 5
pytest -q
```
