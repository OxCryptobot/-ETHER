# @ETHER Status

**Updated:** 2026-08-15 22:12Z — **Phase 3.5 landed + pushed**. Soft launch **BLOCKED**.

## Law
Test after every build. Do not break working paths. Never auto-green soft launch.

## Root cause fixed
`git reset --hard origin/main` was wiping unpublished measure artifacts. Host now:
1. **Pushes measure immediately** after writing rates/snapshot/soft_launch
2. **Rehydrates measure** after every clean_slate
3. **Inlines purge_live_pending** (no more `ss_kill_live_pending` FAIL noise)

## Phase 3.5
| Item | Status |
|------|--------|
| Immediate measure push | **yes** |
| clean_slate → rehydrate_measure | **yes** |
| Kill STEADY job removed | **yes** |
| Tests | `tests/test_phase35_host_hygiene.py` |
| Job | `p3_5_measure_survive` |

Pipeline body **unchanged**. Training wheels **ON**.
