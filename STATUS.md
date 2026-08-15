# @ETHER Status

**Updated:** 2026-08-15 21:28Z — **Phase 3.3 landed**. Soft launch **BLOCKED**.

## Law
Test after every build. Do not break working paths. Never auto-green soft launch.

## Host
Alive. Job `p3_3_measure_first` enqueued.

## Phase 3.3
| Item | Status |
|------|--------|
| STEADY measurement-first | rates → snapshot → soft_launch before heavy packs |
| `scripts/archive_failed.py` | real module |
| `core/soft_launch.py` | ready only if rates + wheels off + `ETHER_SOFT_LAUNCH=1` |
| Tests | `tests/test_soft_launch.py` |
| Pipeline body | **unchanged** |

## Note
Old pending `ss_kill_live_pending_*` jobs still carry the broken `-c` one-liner until drained. New enqueues use `scripts.kill_live_pending`.

Training wheels ON. Soft launch blocked.
