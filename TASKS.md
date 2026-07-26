# @ETHER Task Board

**Updated:** 2026-07-26 (71–75, 77–78 in flight/done)

## Done
| # | Item |
|---|------|
| 66–70 | Process rewards, burst-on-fail, daemon quiz |
| 71 | Side-by-side protocol in METHODOLOGY.md |
| 72 | test_synth + harness in Clear Quartz |
| 73 | ONBOARDING.md |
| 74 | patch_loop (memory/scratch only) |
| 75 | Contextual bandit select(context) |
| 77 | expand_holdout.py → up to 40 tasks |
| 78 | pipeline_hooks prepare_code_for_sandbox |

## Next
| # | Task |
|---|------|
| 76 | Cost/latency ledger panel in Matrix |
| 79 | compare_YYYYMMDD runner for side-by-side logs |
| 80 | Scratch multifile curriculum tier |
| 81 | Pipeline uses bandit_context + prepare_code_for_sandbox on every run |

## Pull
```powershell
git fetch origin; git reset --hard origin/main
python scripts/expand_holdout.py
pytest -q
```
