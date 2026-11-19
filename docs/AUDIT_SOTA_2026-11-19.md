# ETHER diagnostics + batch 1 — 2026-11-19 (branch `ether-batch1`, base `1c92acf`)

Diagnosed from the public repo on Linux (CPU only, Python 3.13 venv). The Windows host was not reachable from
here, but origin shows it ticking: 56 `1650 host_main` commits in the 24 h before 16:29 Bogota (UTC-5),
written by the self-hosted Actions runner (`.github/workflows/autonomy-host.yml`, cron */15).

## Status at 1c92acf

| Area | State | Evidence |
|---|---|---|
| host_main | ticks every ~15 min via Actions runner; `alive.ollama: false`; publishes `next_goal: find_add` while `sota` returns `queue empty` | `artifacts/host_main.json` |
| next_goal | **bug**: host_main and the run used different pickers. Run passed only `done` to `next_from`, which returned skipped `find_clamp`, which was then dropped => `queue empty` forever | `core/agent/sota.py:147-151` (base), `scripts/host_main.py:122-128` (base) |
| find_* rungs | **bug**: `search` substring-matched `def add` (nested `def add(...)` helpers in 8 files), unsorted rglob, backslash paths on Windows; `_one` then redirected the edit to that wrong file while the test imports `context_budget` => guaranteed fail. Root cause of `find_clamp: tests failed` (trace hit `core\batch_queue.py`, 2026-11-07) | `core/agent/skills.py:11-24`, `core/agent/sota.py:276-283` (base) |
| infra vs lesson | **bug**: an Ollama outage made `_one` record `no edit`, which permanently skips the goal (skip is permanent by design) | `core/agent/sota.py:299-301` (base) |
| context budget | **bug** (934dda3): `slice_to_budget` capped at fixed `budget_of(8192)`=7200 while `is_over` uses `ETHER_MODEL_CTX`; at ctx 4096 the slice is 7200 > 5732 => over the cap. Docstring promised matching lines; it truncated the head. Duplicate `def fits` | `core/kernel/context_budget.py:49-56,102-109` (base) |
| gems | `gems.chain` is a deterministic rule bag (security/route/profile/fabricate/memory/evolve); no learned weights; `evolve` = "note not in last lesson" | `core/agent/gems.py:99-128` |
| react | 3 turns, repeat-stop, security stop, gem chain after each tool | `core/agent/react.py` |
| learn ladder | hand-written 12-rung ladder; after `next_bug` the queue is empty again (no generator for new rungs) | `core/agent/learn.py:20-160` |
| sota.json | 69 kept goals (13 ladder/budget + 56 `describe_*`), skipped: describe_extra_tools, find_fits, describe_tombstone, find_clamp; last kept describe_worktree 2026-11-10 | `artifacts/sota.json` |
| honesty of the sota loop | prompts contain the exact function to write ("Write only this function" + skeleton; "Copy this and nothing else"). A pass shows the 4B can copy, not solve. Now flagged per trajectory as `spoiler` | `core/agent/sota.py:241-264` |
| learning path | `core.learning.BanditPolicy` exists (epsilon-greedy contextual, 7 arms) but the sota loop never used it; its state path is module-relative, i.e. inside the Actions checkout on the host | `core/learning.py:14,215` |
| worktree | `core/kernel/worktree.py` keeps passing edits in `edit_ws/` git; publish uses stash+rebase (`sync.ahead:1, dirty:true, note: stash_rebase`) | `artifacts/host_main.json` |
| docs drift | `PRODUCT.md` says "There is no ETHER.exe"; `ETHER.md`/`config/KERNEL.md` say ETHER.exe is the only writer; actual writer today is `scripts/host_main.py` under the Actions runner | files cited |

## Tests (Linux, CPU, serial, `--timeout 120`)

| | collected | pass | fail+error | skip |
|---|---:|---:|---:|---:|
| main 1c92acf | 1696 | 1534 | 79 (78 + 1 collection error `tests/test_unison.py`) | 83 |
| ether-batch1 | 1720 | 1558 | 79 (same set, 0 regressions) | 83 |

The 79 pre-existing failures cluster in legacy Pipeline wiring (`test_pipeline_defects` 11, `test_bandit_design` 8,
`test_loop_verify` 7, `test_topology` 5, ...). A full run also rewrites ~156 tracked/untracked paths under
`artifacts/` (tests write live state).

## Ranked gaps

1. **P0 ladder stuck** (`queue empty` while next_goal=find_add) — fixed (7b23c4a).
2. **P0 find_* rungs cannot pass** (search + redirect) — fixed (7b23c4a).
3. **P0 infra burns goals** — fixed (7b23c4a).
4. **P1 sota loop does not learn from outcomes** — fixed: honest-gate reward into the existing bandit, trajectories, gated promote (58a8442).
5. **P1 spoiler prompts**: ladder passes are copy tasks. Open; now measurable (`spoiler` share in trajectories).
6. **P1 ladder exhaustion**: after `next_bug` nothing new is generated. Open.
7. **P1 tests write live `artifacts/`** (~156 paths per run) — dangerous if FAST pytest runs in the writer's root. Open.
8. **P1 Ollama down on host** (`alive.ollama:false`) — host-side.
9. **P2 slice_to_budget over cap** (934dda3) — fixed (7b23c4a).
10. **P2 79 failing tests / 1 collection error** in legacy pipeline — open.
11. **P2 docs drift on ETHER.exe vs host_main** — open.
12. **P3 `room_left` uses fixed 8192 while `is_over` honours ETHER_MODEL_CTX** — open (changing it would break a kept goal's test on a small-ctx host).

## Measured before/after

- Ladder replay (copy of published sota.json, compliant mock 4B, 3 ticks): main 0 goals kept (`queue empty` x3);
  branch +2 (`find_add`, `next_bug`), then `queue empty` (gap 6).
- New tests: 10 ladder/budget tests — 8 fail on main, 10 pass on branch; 8 outcome tests; 7 ES tests.
- Neuroevolution: see `docs/NEUROEVOLUTION.md` (ES does not beat the bandit; kept off).
