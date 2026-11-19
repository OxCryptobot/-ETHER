# ETHER diagnostics + batch 2 — 2026-11-19 (branch `ether-batch2`)

Base: origin/main `bdfe1f04a` (17:51 ET), the live 1650 under the ETHER-Host
supervisor since 17:13 ET. Measured from origin artifacts and git history, plus
a Linux CPU venv (Python 3.13) on the box. Times are ET (UTC-5).

## Live status at the base

| Area | State | Evidence |
|---|---|---|
| supervisor | running, cycle 57, 0 failures, pull ok, ollama ok; passes 18.7-71.9 s (mean 26.2 s over 58 cycles); `next_in_s` 12 | `artifacts/supervisor.json` history |
| app_alive | fresh, `ollama: true` | `artifacts/app_alive.json` |
| host_main | `next_goal: none`, `seed_depth 0`, `sota: queue empty`; `plan_error: ImportError` every tick (`heartbeat_plan` deleted by a host publish on 11-07) | `artifacts/host_main.json` |
| throughput | 116 host commits 17:13-17:51 (one push every ~20 s; two publishes per pass); 46 distinct sota ticks | `git log 5f15b14..bdfe1f04a` |
| kept vs attempted | 43 kept in 46 ticks; 32 ticks ended `tests failed` (describe goals in core/loop), then the seed ran dry at 17:45 | `host_main.json` history |
| edit quality | 43/43 kept edits were filler: 40 `describe()` returning the module name, `add_name()`→'add', `clamp_name()`→'clamp', `failing_test()`→'found'. Every prompt contained the function to write | `git diff 5f15b14..bdfe1f04a -- core` |
| filler in tree | 89 stubs (describe x72, count_defs template x12, ready, add_name, clamp_name, failing_test, fits_name) | removed in "batch2 cleanup" |
| publish clobber | the worktree publish copied whole stale files over newer origin/main and reverted 3 real fixes: `heartbeat_plan` (11-07), `edit_tx` snapshot wipe (11-04), `argv_allow` "-c" block (11-04, a security regression: `python -c "import scripts..."` was allowed from a job file) | `git show eba54abc9 e20c4782a 183af9f1d` |
| learning path | bandit got reward per kept goal (`learn: arm default, kind pass, reward 0.75, promote hold`), but with exploration off only `default` was ever pulled, so no other arm could reach 3 passes: promotion could never fire. Trajectories live in gitignored `memory/learning/` (not published) | `host_main.json` `sota.learn` |
| context budget | fixed in batch 1; batch-2 prompts measured: 189 prompts (27 goals x 7 arms) per ctx, 0 over budget at ctx 2048/4096/8192 (max 2864/5728/7189 chars vs 2864/5732/7200) | `goal_source.build_prompt` |
| gems / react | unchanged rule bag; react 3 turns (2 for real goals) | `core/agent/gems.py`, `react.py` |
| git growth | `artifacts/host_agent_log.txt` (100 MB, in .gitignore) was still tracked | untracked in batch 2 |

## Ranked gaps (and what batch 2 did)

1. **The loop rewarded busywork.** Closed: goal-quality guard (`core/agent/goal_quality.py`) rejects filler ids, constant-return tests and spoiled prompts; legacy ladder + describe seeding retired (back only with `ETHER_SOTA_LEGACY=1`); `lost_kept` never requeues filler.
2. **No real goal source.** Closed: `core/agent/goal_source.py` turns failing tests (one test = one goal) and ruff F821/F811/F841 findings into goals; target = repo frame / missing import / the function the test imports and calls; prompt = error + test source + file-local slice, capped by `ETHER_MODEL_CTX`, never the answer. Index `artifacts/goal_index.json`, seeded from `config/goal_seed.json` (25 goals from the final Linux run: 21 failing tests + 4 lint; 54 failures dropped as untargetable or infra), refreshed by an 8-file shard scan every 15 min or when dry. Edit = replace or add one function (AST span), must compile.
3. **Gate without a regression check.** Closed: target test must pass and every test that passed before in the guard suite (test file + importing tests + smoke) must still pass; otherwise revert. `repair_heavy` arm gets a second try with the failure as feedback.
4. **Host publish clobbered upstream code.** Closed: worktree publish skips code paths origin/main changed since the fork; the 3 reverted fixes restored (plus the POSIX chmod bug in `_wipe`); no `reset --hard` for a tree >100 ahead.
5. **Tests dirtied live state.** Closed: session fixture restores `artifacts/` + `memory/`; full run: 156 dirty paths before, 0 after. `test_unison` collection error fixed (`def snapshot` line was lost).
6. **Learning could not change behaviour.** Closed (flag-free, gated): real goal kinds get their own bandit file and promotion key, exploration on by default for real goals (`ETHER_SOTA_EXPLORE=0` turns it off), arms change behaviour (`no_context` drops the file slice, `repo_map_on` adds the signature map, `repair_heavy` retries, others add their prompt line). Trajectories carry `goal_kind`, `spoiler`, `regressions`, `prompt_chars`. Promotion still needs 3 honest passes and a better score.
7. **Tight loop + push churn.** Closed: dry-queue backoff 60→900 s; heartbeat publish throttled to 300 s unless a kept edit is pending.
8. **Open:** function-level edits cannot change module constants (the `argv_allow` oracle replay failed for that reason); weak tests accept cheats (a cheat `heartbeat_plan` passed all its tests); 54 of 79 failures are not targetable yet (assertions on dashboards, stale expectations, multi-module); legacy `core/agent/runtime.py` still injects its own stubs (off the live path); full Windows test time unknown.

## Measured (Linux CPU, box)

| Metric | Before (`414e18e`) | After (`ether-batch2`) |
|---|---|---|
| tests collected | 1754 (+1 collection error) | 1770 (0 errors) |
| pass / fail / skip | 1589 / 82 / 83 | 1611 / 75 / 84 |
| tests that passed before and fail now | — | 0 (1 vacuous test now xfail with reason) |
| previously failing now passing | — | 8 |
| dirty paths after full `pytest tests` | 156 | 0 |
| full run time | 285 s | 298 s |
| filler stubs in core/scripts/gems | 89 | 0 |
| goals with spoiler / constant test handed out | 100% of legacy | 0 (guard) |
| prompts over the ctx budget (189 per ctx) | — | 0 at 2048 / 4096 / 8192 |

Mock replays (`out/*.py`, scratch copies):
- Real-repo loop, 26 seed goals, one attempt each, mock model: oracle kept 1/1 known function fix (`heartbeat_plan`), 24 junk replies edited nothing, 1 oracle fix rejected because the bug sits in a module constant; 211 s total (~8 s per goal for the two guard runs, model time excluded).
- Unit replay (`tests/test_batch2_goal_source.py`): right fix kept with 0 regressions; a fix that passes the target but breaks a passing test is reverted; junk edits nothing.
- Refactor (`docs/REFACTOR.md`): 97 candidates, 96 kept, 1 regression caught; 0 missed regressions in a full-suite check.

## What the live host should show after the push

- `host_main.json`: `next_goal` = a `fix_*` or `lint_*` id; `seed_depth 0`; `real_queue.open` about 25; `plan_error` gone; `sota.kind` = `fix_test`/`lint`; `sota.tried` non-empty; `learning.by_kind`.
- `supervisor.json`: `state: idle` with growing `next_in_s` only when there is no real goal; otherwise passes are longer (two guard runs per attempt).
- Commits: heartbeat-only pushes no more than one per 5 min; a kept goal pushes at once with its code file.
- Honest numbers to watch: kept/attempted for real goals (expected low for a 4B; any kept one is a real repair), regressions reverted, spoiler share 0.
