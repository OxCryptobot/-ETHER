# @ETHER Status

**Updated:** 2026-08-15 21:51Z — **Phase 3.4 landed + pushed to main**. Soft launch **BLOCKED**.

## Law
Test after every build. Do not break working paths. Never auto-green soft launch.

## Host
Alive. Idle path now runs `core.measure_tick` every ~90s (rates + snapshot + soft_launch) and pushes artifacts.
Job `p3_4_measure_tick_verify` enqueued.

## Phase 3.4
| Item | Status |
|------|--------|
| `core/measure_tick.py` | **landed** |
| host idle → measure_tick | **wired** |
| Light push: measure + soft_launch | **yes** |
| Tests | `tests/test_measure_tick.py` |
| Pipeline body | **unchanged** |

## Soft launch
Blocked until: published rates with live rows + wheels off + `ETHER_SOFT_LAUNCH=1`.

Training wheels ON.
