# @ETHER Status

**Updated:** 2026-08-15 19:07Z — **Phase 3 batch landed**. Soft launch **BLOCKED**.

## Law
**Test after every build. Do not break working paths.** Defaults stay safe:
- `ETHER_LOOP_RUNNER=0`
- `ETHER_SYMBOL_INDEX=0`
- LoRA dry-tick only
- Soft launch blocked until rates + mentor sign-off

## Host
Alive. Job `p3_soft_launch_measure` enqueued.

## Phase 3 batch
| Item | Status |
|------|--------|
| Steady: `ss_honest_live_report` | **in STEADY** |
| Steady: `ss_lora_dry_tick` | **in STEADY** |
| Steady: `ss_phase2_regression` | **in STEADY** |
| `core/phase3_snapshot.py` | **landed** |
| Tests | `tests/test_phase3_snapshot.py` |
| Pipeline body rewrite | **not done** (by design — no risk) |

## Next (Phase 3.2 after host green)
1. Read published `artifacts/honest_live_rates.json` + `phase3_snapshot.json`
2. Optional: behavior-preserving wire of `decide_tool_first_terminal` into Pipeline terminal block
3. Expanded hard suite measurement only when mentor requests live runs

Training wheels ON.
