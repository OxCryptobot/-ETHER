# @ETHER Task Board

**Updated:** 2026-07-26 (76–81 shipped)

## Done
| # | Item |
|---|------|
| 66–75 | Intelligence, rewards, burst-on-fail, test_synth, onboarding |
| **76** | `core/ledger.py` + Matrix collector ledger fields |
| **77** | expand_holdout.py (40 tasks) |
| **78–81** | pipeline_hooks, patch_loop, **bandit_context**, **prepare_code**, scratch tier |
| **79** | `scripts/compare_run.py` → memory/bench/compare_YYYYMMDD.* |
| **80** | scratch_multifile curriculum tier |

## Next (optional stretch)
| # | Task |
|---|------|
| 82 | Matrix UI cards for ledger avg_run_ms / burst calls |
| 83 | Auto-append compare table into SCOREBOARD.md |
| 84 | Rate-card optional $ estimate in ledger |

```powershell
git fetch origin; git reset --hard origin/main
python -m pip install -e ".[dev]" -q
python scripts/expand_holdout.py
python -c "from core.ledger import compute_ledger; print(compute_ledger())"
pytest -q
```
