# @ETHER Task Board

**Updated:** 2026-07-26 (76–81)

## Done
| # | Item |
|---|------|
| 66–75 | Intelligence scoreboard, process rewards, burst-on-fail, test_synth, onboarding |
| **76** | `core/ledger.py` cost/latency ledger (Matrix already reads it) |
| **77** | `scripts/expand_holdout.py` |
| **78–81** | pipeline_hooks + pipeline_boot wires contextual bandit + code prep |
| **79** | `scripts/compare_run.py` side-by-side scaffold |
| **80** | `memory/curriculum/scratch_tier.json` |

## Next
| # | Task |
|---|------|
| 82 | Blend scratch_tier into curriculum load_tiers |
| 83 | Matrix UI cards for ledger avg_ms / burst |
| 84 | Auto-write SCOREBOARD after compare_run |
| 85 | Stabilize Windows daemon one-window path |

```powershell
git fetch origin; git reset --hard origin/main
python -m pip install -e ".[dev]" -q
python scripts/expand_holdout.py
python -c "from core.ledger import compute_ledger; print(compute_ledger())"
pytest -q
```
