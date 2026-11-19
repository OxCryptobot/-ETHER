# ETHER batch 3 — 2026-11-19 (branch `ether-batch3`)

Base: origin/main `c18a16155` (18:12 ET, live 1650 host artifact commits only since
batch 2's base `8a673ae56`) + the 7 batch-2 commits rebased on it (clean). Measured on
the box (Linux CPU venv, Python 3.13). Times are ET (UTC-5).

## Live host at the base (origin/main, 18:12 ET)

| Area | State |
|---|---|
| supervisor | running, cycle 96, 0 failures, pass ~19 s, `next_in_s` 12 (old code: no dry backoff) |
| app_alive | fresh (18:12 ET), `ollama: true` |
| host_main | `next_goal: none`, `seed_depth 0`, sota `queue empty`, `plan_error: ImportError` every tick |
| sota.json | 92 goals, 76 of them `describe_*` filler, `kept 92` |
| push rate | 140 host commits in the hour before 18:42 ET (~1 per 25 s) |

All of this is the old code: batch 2 is not on origin yet.

## Gaps closed in batch 3

1. **`plan_error: ImportError` every tick.** Root cause: `core.kernel.plan.heartbeat_plan`
   was deleted on origin by a host publish on 11-07 (whole-file copy over a newer file);
   host_main imports it lazily, so only the exception *name* was logged. Batch 2 commit A
   already restores it (and stops the clobbering publish). Batch 3 adds: `plan_error` now
   carries the message; `tests/test_batch3.py::test_every_lazy_import_on_the_host_path_resolves`
   checks every `from core|scripts|gems… import X` in host_main / host_supervisor / host_ctl
   resolves (fails on origin/main with `core.kernel.plan.heartbeat_plan`, passes here).
2. **Edit granularity.** A reply may carry module-level `NAME = …` assignments with the
   function (`goal_source.extract_edit/apply_edit`). Allowed: names already bound at module
   level (replaced in place) or new names the new function reads (inserted before it); max
   4, no dunders, < 40 lines each, one compiled write, protected-path guard kept, revert on
   gate failure. A failing frame on a module-level line becomes an `assign` goal. Prompts
   show the current constants the function reads (context; the spoiler check now also
   rejects a `NAME = <new value>` line). Flag `ETHER_EDIT_CONSTANTS` (default on, `0` = off).
3. **Goal coverage.** Failure → goal now returns a reason. New targets: `module 'x' has no
   attribute 'y'` as a missing name; `import a.b as c` / `from a import mod` + `c.f(`; the
   deepest non-protected frame instead of giving up on a protected one; module-level
   frames; and spectrum-based fault localisation (`core/agent/fault_loc.py`, Ochiai over the
   repo functions each test entered, recorded by a self-contained pytest plugin during the
   normal scan; flag `ETHER_SBFL`, default on, ~+50% scan time). SBFL goals rank last
   (tractability −0.2), need suspicion ≥ 0.3, are skipped when the test only exercises
   protected code, and failed tries are shared per (file, symbol) with a cap of 6, so one
   wrong suspect cannot eat the queue.
4. **Weak tests.** The gate now also requires every other open failing test in the same
   test file that targets the same symbol to pass ("siblings"); kept edits resolve them.
   New `heartbeat_plan` contract tests (full truth table, keyword-only, follows the
   PlanGraph). The batch-2 cheat passes `test_stale_plan_does_not_edit` but not its siblings.
5. **Stale asserts** (corrected, none deleted): `test_unison` goal order (runtime/self-grow
   goal first since 10-30), `unison.json` is published since `5539923a5` (assert it is in
   PATHS and the observer writes only that file); `test_publish_sync` Actions tick runs
   `_learn` (core.agent.sota) and arms self_heal since `684bfbc9c`, still no ollama/runner/
   keepalive/drain.
6. **Learning visible from GitHub.** `artifacts/learning_summary.json` (in publish PATHS),
   written each host tick by `outcome.publish_summary`: totals, explore flags, promoted arms,
   per-kind × per-arm pulls/passes/pass_rate/mean_reward/regressions, real_queue with drop
   reasons, last 25 trajectories. Whitelisted fields, ids sanitised and capped at 80 chars,
   no prompts/replies/env/tokens, ≤ 16 KB. `memory/` stays unpublished.
7. **Legacy runtime stub injection.** `core/agent/runtime.py` had 4 sites that wrote a
   `count_defs()`/`fits()` stub when the model did not and counted it as kept. All removed;
   the per-module `count_defs() >= 1` goals are gone; only the model's own edit is applied, it
   must define the goal symbol, protected paths are refused. The xfail test is replaced by 3
   real tests (no-op edit keeps nothing, real edit kept, protected path refused).

## Measured

| Metric | Before (batch 2 rebased, `56c1958f8`) | After (`ether-batch3`) |
|---|---|---|
| tests collected | 1770 | 1790 |
| pass / fail / skip(+xfail) / errors | 1606 / 76 / 88 / 0 | 1629 / 73 / 88 / 0 |
| passed before, fail now | — | 0 |
| fixed | — | 3 (test_unison x2, test_publish_sync) |
| same, with ruff on PATH (5 verifier lint tests stop skipping) | — | 1635 / 72 / 83 / 0 (290 s) |
| full run time | 302 s | 299 s |
| dirty paths after full `pytest tests` | 0 | 0 |
| failing tests that become goals | 21 of 76 (+4 lint = 25 seed) | 51 of 74 (+4 lint = 55 seed); 20 without SBFL |
| prompts over ctx budget (385 = 55 goals × 7 arms) | 0 | 0 at 2048 / 4096 / 8192 |
| prompts rejected by the quality guard | — | 0 / 385 |

Drop reasons now (74 failing): 16 `no_repo_target` (static/topology checks over many files,
pipeline tests whose suspects score < 0.3), 4 `protected_target` (dashboard moonshot tiles),
2 `source_text_assert` (tests that grep source files), 1 `infra` (docker). Before batch 3
they were one bucket (`infra_or_untargetable`): of the 55, 46 bare asserts with no repo frame,
4 protected, 3 source-text, 1 infra, 1 module alias.

Mock-model replay on a scratch copy with origin/main's broken `plan.py` (no
heartbeat_plan) and `argv_allow.py` (`-c` hole) — `docs/results/batch3/replay3.py`:

| Mode | Goals | Kept | Result |
|---|---|---|---|
| cheat (constant answers) | 4 | 0 | all rejected; both files unchanged |
| right function, no constant | 4 | 1 | heartbeat_plan kept (3 goals resolved); argv rejected: needs `ALLOWED_MODS` |
| oracle (function + constant) | 4 | 2 | both kept, 0 regressions, `-c` hole closed, 0 failing |

## Remaining gaps (ranked)

1. **SBFL precision is unmeasured and looks low.** 24 of 31 SBFL goals point at
   `GemRegistry.execute`; a manual check of `test_pipeline_happy_path_mocked` shows the real
   cause is the pipeline's `tool_runtime` stage (`run_if_enabled returned None`). Shared-try
   cap bounds the cost to 6 attempts per suspect. Next: score with the error text (IR) and
   drop failure-path-only helpers; measure kept/attempted per `via` from learning_summary.
2. **Batch 2+3 are not live.** The host still runs the filler loop and pushes ~2/min.
3. **16 failures have no target** (topology/static checks, stage-contract tests): need
   multi-file or file-level edits.
4. **No real-model numbers.** All replays use a mock model; first hour on the 1650 decides.
5. **Lint goals need ruff in the host venv.** `ruff_bin()` now also looks next to the
   interpreter (pythonw's PATH lacks `.venv\Scripts`), but ruff is only in the `dev` extra;
   if `.venv\Scripts\ruff.exe` is missing, lint goals stay empty (check `learning_summary.json`
   `real_queue`).
6. Windows full-suite time unknown; SBFL overhead measured on Linux only (+50%).
