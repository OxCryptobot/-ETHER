# @ETHER Task Board

**Updated:** 2026-07-26

## Done recently
- Linux local sandbox + auto docker→local fallback
- doctor sandbox-aware (no false Docker fail on cousin box)
- start_daemon_linux.sh
- COUSIN.md / ONBOARDING.md dual profile (Qwen 3.6)
- Scoreboard / weekly / hidden / dataset / ablation tooling

## Operator (cousin owns quality)
1. Set exact Qwen 3.6 tag in `.env`
2. `ETHER_SANDBOX_BACKEND=local`
3. `python scripts/weekly_scoreboard.py`
4. Optional `burst_ablation.py` only for science
