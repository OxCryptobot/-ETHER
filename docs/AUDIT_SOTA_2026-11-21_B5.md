# ETHER batch 5 — 2026-11-21 (branch `ether-batch5`)

Base: origin/main `61c286df5c` (11:34 ET, only live `1650 host_main` artifact commits since
batch 4's base) with batches 2–4 (16 commits) rebased on it cleanly, then batch 5 on top.
Measured on the box (Linux CPU venv, Python 3.13). Times are ET (UTC-5).
Doctrine kept: single writer (host_main via host_supervisor), tool-first, honest gate
(tool edit + passing test, generate-only never counts), 1650 / qwen3.5:4b, matrix read-only,
no second installer.

## Live host at the base (origin/main, 11:34 ET)

| Area | State |
|---|---|
| host_main.json | `plan_error: ImportError` every tick, `next_goal: none`, sota `queue empty`, `seed_depth 0` |
| alive / ollama | fresh, `ollama: true` |
| push rate | 5769 `1650 host_main` commits in the 24 h before 11:34 ET (≈240/h); plus 1 medic + 1 enqueue commit (Matrix/Actions, ≈1/day) |
| pending jobs | 31 stale non-edit jobs (22 `gem_energy_publish`, 9 `medic_hb`) never drained by the host |

All of this is still the pre-batch-2 code: batches 2–5 are not on origin yet.

## Full suite (same box, same venv)

| | total | pass | fail | error | skip |
|---|---|---|---|---|---|
| before (rebased b2–b4) | 1816 | 1661 | 72 | 0 | 83 |
| after (batch 5) | 1848 | 1693 | 72 | 0 | 83 |

New failures: **0**. The 72 failures are identical (they are the goal pool). +32 tests
(`tests/test_batch5.py`). Dirty paths after the suite: **0** (artifacts/ and memory/ restored).
Detail: `docs/results/batch5/tests_summary.json`.

## 1. Dispatcher targets (`ETHER_SBFL_RANK`, default `b5`)

`core/agent/fault_loc.py`: the scan plugin now also records caller→callee edges per test
(≤1200, test stubs keyed `~tests/...`). `rank5` = batch-4 hub rank, then
(a) a **dispatcher** (a method whose callees include ≥2 distinct same-name methods, e.g.
`GemRegistry.execute` → `Citrine.execute`, `ClearQuartz.execute`…) is demoted ×0.2 and its
score passes to the handlers this failing test actually reached (×0.9), and (b) the failure
text votes (below). The fan-out rule (≥10 callees) is off: it marked 99 orchestrators.

Live scan (74 failing tests, 31 SBFL goals, quiet box):

| ranker | `GemRegistry.execute` share | largest single target share | distinct targets |
|---|---|---|---|
| ochiai | 0.774 | 0.774 | 4 |
| hub (batch 4) | 0.355 | 0.355 | 10 |
| **b5** | **0.0** | **0.29** | **13** |
| b5 + fan-out rule | 0.0 | 0.258 | 12 |

Injected-bug bench (`sbfl_bench5.py`, scratch copy, one mutant per function, tests that
only fail in the bare-assert way SBFL serves, F set = 66 tests):

| ranker | top-1 | top-3 | found | mean rank |
|---|---|---|---|---|
| ochiai | 0.606 | 0.879 | 0.955 | 2.57 |
| hub | 0.788 | 0.864 | 0.970 | 1.92 |
| b5 without failure text | 0.788 | 0.864 | 0.970 | 1.92 |
| **b5** | **0.818** | **0.894** | **0.985** | **1.46** |

Dispatcher-handler set (D: 8 handlers reached through `GemRegistry.execute`, 4 mutants
each = 32): only **3** failing tests resulted — the suite barely checks gem handler output
(ranked gap 2). On those 3: top-1/top-3 0 for every ranker; mean rank hub 53.3 → b5 22.7.
Small n; reported, not claimed.

## 2. Failure text in localisation

`fault_loc.evidence()` reads the failing test's message: pytest `where X = f()` names
(+0.35), string/number literals found in a candidate's source span (+0.30), traceback
frames inside candidates (+0.25). On the F set this is the whole b5 gain
(`b5_noev` = hub). Frames are already used directly by the frame goal path; the D bench
ignores them on purpose.

## 3. Multi-target edits (`ETHER_MULTI_EDIT=1`, default off)

`core/agent/multi_edit.py` + `core/kernel/edit_tx.FileTx` (per-file snapshot, created
files/dirs removed on revert). ≤3 places, all-or-nothing: one reply with `# file: <path>`
blocks, every path must be in the goal, protected-path guard, compiled writes, then target
test + sibling tests + guard suite; any failure reverts every file. Kinds: missing module
(new file ≤150 lines), small syntax-error file (≤80 lines), ≤3 failing sites; and
escalation places (frame / SBFL ≥0.7 of top / test-import alternatives) used only after one
single-target try failed. `trim_to_fit` drops places until the reply fits the cap.

| | goals | multi-only goals | goals with escalation places | dropped `no_repo_target` |
|---|---|---|---|---|
| batch 4 classifier | 45 | 0 | 0 | 16 |
| b5, multi off | 47 | 0 | 0 | 14 |
| b5, multi on | 47 | 0 | 29 | 14 (3 topology tests → `too_many_sites`, 12–40 sites) |

+2 goals come from the package-`__init__` module fix (`mod_rel`), not from multi. Honest
correction: batch 4's "16 multi-file failures" was wrong — only 3 failures are really
cross-file and all exceed the 3-place cap; the rest are source-text asserts, protected or
dashboard code, or data. Context: multi prompts never exceed the budget — 2K max
2612/2864, 4K 3870/5732, 8K 3977/7200, 0 dropped.

Mock replay (`replay5.py`, tmp git repo, real gate):

| scenario | kept | why |
|---|---|---|
| oracle 2-file fix (after a failed single try) | yes | 0 regressions |
| cheat: constant makes target pass | no | 2 regressions → reverted |
| cheat: edits the test file | no | path not in the goal |
| half fix (1 of 2 files) | no | tests failed → both files restored |
| new module correct | yes | |
| new module wrong | no | file removed |
| new module + writes a test | no | path not in the goal, file removed |

## 4. Publish noise (`ETHER_PUBLISH_MIN_S=300`)

Every publish path goes through `origin_publish.publish` (host_main twice per tick; heal,
medic and enqueue artifacts are written locally and ride on that publish; the medic and
enqueue commits on origin come from Matrix/Actions, ≈1/day, read-only). The bypass was the
batch-2 "dirty ⇒ urgent" rule: artifacts are dirty every tick. Now urgent means
`publishable_code()` — code that would really change origin. host_main.json is written
before publish, so origin shows this tick.

Simulated 24 h (`publish_sim.py`):

| model | commits/h |
|---|---|
| old (measured 240/h on origin) | 232.3 |
| batch 2 | 28.6 |
| **batch 5, busy** | **12.0** |
| batch 5, dry queue | 4.0 |

## 5. Startup self-check, post-pull smoke, rollback

- `scripts/host_selfcheck.py`: resolves every lazy `from core|scripts|gems… import X` in the
  host modules and compiles them. On the old origin/main it reports exactly
  `scripts/host_main.py:193 core.kernel.plan.heartbeat_plan: ImportError: cannot import name 'heartbeat_plan'`.
- host_main runs it at tick start: `health: degraded`, `selfcheck_error`, host_main.json
  written immediately; every `*_error` now has name + message.
- Supervisor: after a pull that moves HEAD it runs `host_selfcheck --smoke`
  (`ETHER_SMOKE=0` off, timeout `ETHER_SMOKE_TIMEOUT_S`) before host_main.
  `ETHER_PULL_ROLLBACK=1` (default off) → local `git reset --keep` to the last good commit
  (`.git/ether_host_good`) and a pin (`.git/ether_host_pin.json`); pulls skip while pinned
  until upstream code changes; publish goes through the origin worktree when pinned. Never
  `--hard`, never pushes. Tested with real tmp git repos.

## 6. Tick-path audit (ranked, things that block learning)

| # | finding | status |
|---|---|---|
| 1 | 31 stale non-edit pending jobs kept the supervisor in 12 s busy cadence | fixed: idle cadence counts only jobs a host drainer runs |
| 2 | Ollama got no `num_ctx` → 4B default ctx could truncate prompts silently | fixed: `ETHER_NUM_CTX` (4096) sent; timeout scales with it |
| 3 | dirty ⇒ urgent publish bypassed the throttle | fixed (§4) |
| 4 | host_main.json written after publish (origin one tick stale) | fixed |
| 5 | errors kept only the exception type | fixed |
| 6 | ruff missing on the host → lint goals empty | reported by selfcheck; `pip install ruff` in apply steps |
| 7 | publish twice per tick | covered by the throttle; left |
| 8 | stale Matrix jobs never drained | Matrix read-only; left |

## Flags

| flag | default | effect |
|---|---|---|
| `ETHER_SBFL_RANK` | `b5` | `hub` / `ochiai` restore batch 4 / 3 |
| `ETHER_MULTI_EDIT` | off | `1` = multi-target transactional edits |
| `ETHER_PUBLISH_MIN_S` | 300 | throttle; urgent only for publishable code |
| `ETHER_SMOKE` | on | `0` skips the post-pull smoke |
| `ETHER_SMOKE_TIMEOUT_S` | 300 | smoke timeout |
| `ETHER_PULL_ROLLBACK` | off | `1` = local rollback + pin on smoke failure |
| `ETHER_NUM_CTX` | 4096 | Ollama context |

## Remaining gaps (ranked)

1. **Nothing above runs until batches 2–5 are pushed**: origin still logs `plan_error: ImportError`, queue empty.
2. Gem handler outputs are barely tested (32 handler mutants → 3 failing tests); SBFL can't localise what tests don't check. Add handler contract tests (reviewed, not by the host).
3. 3 topology failures need 12–40 sites: refactor-sized, beyond multi-edit; human or a refactor goal.
4. 14 `no_repo_target` + 6 `too_large` drops; too_large needs function-slice edits.
5. Multi-edit is unproven live: turn on `ETHER_MULTI_EDIT=1` after a day of single-target kept/attempt numbers.
6. ruff on the host; stale Matrix job queue (read-only).

Results: `docs/results/batch5/` (sbfl_bench5.json, goalable_b4/b5.json, replay5.json,
publish_sim.json, tests_summary.json). Seed regenerated: 47 failing-test goals + 4 lint
(drops: protected 4, no_repo_target 14, too_large 6, source_text_assert 2, infra 1).
