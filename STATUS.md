# @ETHER Live Status

## Learning (honest)
**Not** full RLHF / LoRA on this GPU class.

**Real ML-lite now in:**
- Reward from sandbox exit + confidence + audit
- Experience store: `memory/learning/experience.jsonl`
- Epsilon-greedy bandit over strategies: `memory/learning/bandit.json`
- Pipeline selects strategy each run and updates from outcome

`ETHER_LEARNING=1` (default). Disable with `0`.

## Autonomy
Flywheel PASS/FAIL reports continue.
Dashboard: `ether dashboard` → http://127.0.0.1:8787
