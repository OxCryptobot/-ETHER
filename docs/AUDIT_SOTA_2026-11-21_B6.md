# ETHER batch 6 — 2026-11-21 (branch `ether-batch6`)

Base: `origin/main` @ 25cafe9ffb (14:10 ET), batches 2–6 on top (28 commits). Not pushed (box token 401; user pushes).
Rules kept: ETHER only, GOPHER/matrix untouched, author OxCryptobot, no secrets, single writer, honest gate, 1650/4B.

## Live host (origin/main, 14:10 ET) — still old code

`python scripts/first_hour_report.py --ref origin/main` (new, see §4):

```
ETHER first-hour report  ref=origin/main  head=25cafe9ffb 2026-11-21T14:10:34-05:00 1650 host_main
host: tick 2026-11-21T19:10:02.241615+00:00  health=n/a (pre-batch-5 host)  selfcheck_error=-  plan_error=ImportError
      next_goal=none  sota=queue empty kept_n=0  seed_depth=0
learning: learning_summary.json missing
commits: 237 in 1.000 h = 237.8/h  (host_main 237, other 0)  authors {'ether-exe': 237}
```

The host is alive and publishing, but on pre-batch-2 code: `plan_error=ImportError`, `sota: queue empty`, `next_goal=none`,
no `learning_summary.json`. All commits are host_main artifact commits (no code drift since batch 5's base). Nothing below
has run on the host yet. Batches 2–5 are still not on origin/main.

## Full suite (same box, same venv, `pytest tests -q -p no:cacheprovider`)

| | tests | pass | fail | skip |
|---|---|---|---|---|
| before (batch-5 head rebased) | 1848 | 1692 | 73 | 83 |
| after (batch-6 head) | 1935 | 1778 | 74 | 83 |

- New failures: `test_grandidierite_generate_scaffolds_into_quarantine`, `test_rose_quartz_stream_empty_content_is_an_error` (only the deliberate real-bug tests, §1).
- Fixed: `test_new_module_goal_creates_a_small_file_and_reverts_a_wrong_one` (the batch-5 flake, root cause: stale bytecode, §4).
- `git status --porcelain` after the run: 0 dirty paths.

## 1. Gem handler contract tests (`tests/test_gem_contracts.py`, written by the batch-6 reviewer for human review)

The file header marks it as reviewer-written, not host-written. 57 test functions cover `GemRegistry.execute` routing and all
eight handlers (Labradorite, BlackTourmaline, Amethyst, Selenite, Grandidierite, Citrine, ClearQuartz, RoseQuartz). Network,
Qdrant and the LLM are faked with `httpx.MockTransport` and in-memory fakes. The tests assert real outputs (payload fields,
error envelopes, files written, request bodies), not constants. No handler code was changed.

Planted-bug bench `docs/results/batch6/gem_mutation6.py` → `docs/results/batch6/gem_mutation6.json`. It makes every
compare-flip and int+1 mutant inside each gem's `execute` (63 mutants) and runs them on a scratch copy only.
"before" = every passing test whose spectrum covers the handler. "after" = the same tests plus the contract tests.

| | mutants | killed before | killed after | kill rate | b5 top-1 / top-3 | hub top-1 / top-3 | host goal = mutated method |
|---|---|---|---|---|---|---|---|
| all `execute` | 63 | 8 | 43 | **0.127 → 0.683** | 0.671 / 0.904 | 0.418 / 0.719 | 0.075 (b5 classifier) → **0.562** (b6) |
| batch-5 D-set subset | 24 | 6 | 16 | 0.25 → 0.667 | 0.621 / 0.924 | 0.379 / 0.727 | 0.061 → 0.394 |

Localisation is measured over the 146 newly failing (test, mutant) pairs. "Host goal" means `classify_failure` makes a goal
whose target is the mutated method. In batch 5 that almost never happened, because the large `execute` methods failed the
reply-size gate. Batch-6 span goals (§2) fix that.

| handler | mutants | killed before → after | b5 top-1 | host target |
|---|---|---|---|---|
| Labradorite | 19 | 0 → 17 | 0.92 | 0.92 |
| RoseQuartz | 13 | 0 → 5 | 0.00 | 0.00 |
| Grandidierite | 9 | 1 → 7 | 0.733 | 0.633 |
| ClearQuartz | 7 | 4 → 4 | 0.30 | 0.30 |
| Citrine | 6 | 2 → 6 | 0.50 | 0.107 |
| Selenite | 5 | 1 → 1 | 0.50 | 0.50 |
| Amethyst | 3 | 0 → 3 | 0.667 | 0.444 |
| BlackTourmaline | 1 | 0 → 0 | n/a | n/a |

Correction to batch 5: its "32 planted bugs → 3 failures" used only the 3 smallest covering test files. With every covering
test it is 8/63 here (12.7%). The gap was still real: 55 of 63 handler bugs were invisible to the suite.

Survivors: 20 mutants (RoseQuartz 8, Selenite 4, ClearQuartz 3, Grandidierite 2, Labradorite 2, BlackTourmaline 1); per-mutant rows are in the JSON.
RoseQuartz localisation is 0 because SBFL ranks the `_call*` helpers above `execute`. Those helpers are the right edit
place for most of its bugs, so this is a measurement artefact rather than a missed bug.

**Real bugs found. Left as failing tests (no xfail) and as host goals (they are in the regenerated seed as `fix_test` goals, but mistargeted, see §2):**

1. `test_grandidierite_generate_scaffolds_into_quarantine`. `Grandidierite.TEMPLATES` contains a literal `{"ok": ...}` and
   is passed through `str.format`, which raises `KeyError('"ok"')`. The default `generate` action therefore always returns a
   RUNTIME error envelope. Fix: escape the braces (`{{"ok": ...}}`) or use `string.Template`.
2. `test_rose_quartz_stream_empty_content_is_an_error`. `RoseQuartz._call_stream` returns success with `content=''`, while
   the non-stream path treats empty content as an error. Fix: the same empty-content check in the stream path.

## 2. The 20 undropped-but-ungoalable failures (14 `no_repo_target` + 6 `too_large`)

New mechanism: **span goals** (`ETHER_SPAN_EDIT`, default 1; `core/agent/span_edit.py`). When the best target is too large
for the reply cap, the goal becomes a window of at most 30 lines inside it, shrunk in ×2/3 steps down to 6 lines until it
fits the cap. The window is anchored on, in order:

1. the traceback frame line;
2. the failing assert's own literal (score ≥ 2);
3. evidence words.

The prompt shows the window between `# >>> EDIT START` / `# <<< EDIT END`, with 4 read-only lines on either side.
`apply` enforces these checks:

- a sha stale-guard;
- re-indentation;
- the result must compile;
- the target must still exist;
- the protected-path guard.

The gate is unchanged: a span edit is kept only if the failing test passes and the guard suite does not regress.

Other honest reclassifications in `classify_failure`:

- `test_bug`: the test itself references an undefined name.
- `too_many_sites`: more than 3 distinct sites when multi-edit is off.
- `source_text_assert`: broadened to `inspect.getsource(` and to path joins.
- **test-imported constant → assign goal**: an UPPER constant imported by the test and read by the failing assert, at most
  80 lines, or a span if larger.
- SBFL: a too-large suspect that outranks the best fitting one by ≥10% becomes a span goal, but only on a strong anchor
  (score ≥ 2).

Per-test classification (`docs/results/batch6/classify20.json`):

| test | batch 5 | batch 6 | target / reason |
|---|---|---|---|
| dashboard `test_holdout_wiring_reflects_curriculum_coverage` | no_repo_target | no_repo_target | env/data: curriculum_tasks = 0 on the box |
| dashboard `test_posture_is_quiet_when_everything_is_off` | no_repo_target | no_repo_target | env: "sandbox not isolated" (no docker on the box) |
| `test_pipeline_run_shadows_write_progress` | no_repo_target | source_text_assert | asserts on `inspect.getsource(Pipeline.run)` |
| `test_pipeline_run_source_calls_annotate_all` | no_repo_target | source_text_assert | same |
| `test_pipeline_run_walks_plan` | no_repo_target | source_text_assert | same |
| `test_pipeline_source_resume_and_dispatch` | no_repo_target | source_text_assert | same |
| `test_pipeline_executes_dispatched` | no_repo_target | source_text_assert | same |
| `test_host_agent_stand_down_wired` | no_repo_target | source_text_assert | greps a script's text |
| `test_stage_contract_stable` | no_repo_target | test_bug | test uses `STAGE_CODE` without importing it |
| `test_steady_has_phase3_templates` | no_repo_target | **goal** | span on `scripts/foreman.py::STEADY_TEMPLATES` 105–134 |
| topology `test_d1_…` | no_repo_target | too_many_sites | 18 sites (§3) |
| topology `test_d2_…` | no_repo_target | too_many_sites | 20 sites (§3) |
| topology `test_d2_hard_…` | no_repo_target | too_many_sites | 14 sites (§3) |
| topology `test_d3_no_new_state_writers` | no_repo_target | no_repo_target | refactor kind instead (§3) |
| `test_doctor_mentions_hygiene` | too_large | **goal** | SBFL `scripts/ether_cli.py::cmd_doctor` |
| `test_whats_next_signals` | too_large | **goal** | span `write_whats_next.py::main` 113–142 (assert literal) |
| `test_whats_next_no_dual_dashboard_blocker` | too_large | **goal** | same span |
| `test_phase3_canaries` | too_large | **goal** | SBFL `AgentState.__init__` (low confidence: the assert is only `ok is True`) |
| `test_grading_does_not_write_to_the_host` | too_large | **goal** | span `core/holdout.py::grade_against_holdout` 69–98 |
| `test_grading_runs_the_code_it_was_given` | too_large | **goal** | span `grade_against_holdout` 141–170 |

There were no missing-module failures among the 20, so the batch-5 new-module goal did not apply to any of them.

Goalable on the same failing set (multi off, reply gate on):

| | goals | protected | no_repo_target | too_large | source_text | too_many_sites | test_bug | infra |
|---|---|---|---|---|---|---|---|---|
| batch 5 | 47 | 4 | 14 | 6 | 2 | – | – | 1 |
| batch 6 | **54** | 4 | 3 | **0** | 8 | 3 | 1 | 1 |

Full batch-6 run on the post-suite failing set (`docs/results/batch6/goalable_b6.json`, 76 failing = the 74 above plus the
2 deliberate contract failures):

| config | goals | span goals | too_large | distinct targets | largest share of one target |
|---|---|---|---|---|---|
| batch 6, multi off | 56 | 11 | 0 | 35 | 0.125 (`GemRegistry.register`) |
| batch 6, `ETHER_SPAN_EDIT=0` (ablation) | 55 | 0 | 1 | 32 | 0.182 |

Without spans, most of the former too-large failures still become goals, because they fall back to a smaller SBFL suspect.
Spans add 1 goal, but they move 11 goals onto the top-ranked function. That raises host-target accuracy on the handler
bench from 0.075 to 0.562 (§1) and lowers target concentration.

**Caveat:** the 2 real gem bugs become goals, but on the wrong targets:

- Grandidierite → `core/schemas.py::ResponseEnvelope.xor_error_and_payload`.
- RoseQuartz → `core/model_select.py::resolved_primary`.

The handler catches the exception, so there is no frame, and SBFL prefers the shared helpers. The gate will reject wrong
edits, so this is safe, but they will probably not be fixed until anchoring improves (gap 4).

`config/goal_seed.json` is regenerated (`docs/results/batch6/seed6.py`): 60 goals (56 fix_test + 4 lint). Dropped with a
named reason: protected 4, source_text 8, too_many_sites 3, no_repo_target 3, test_bug 1, infra 1.

The 20 became 7 goals. The other 13 are now named for what they are, so they no longer count as unexplained drops.
The same span path raised host-target accuracy on the gem bench from 0.075 to 0.562 (§1).

## 3. Topology failures → refactor-kind codemods (`ETHER_REFACTOR=1`, honest gate)

`docs/results/batch6/topology6.py` → `topology6.json`. It runs on a scratch copy. Each attempt runs the guard suite before
and after, and reverts on any regression. For each strategy:

| test | sites before | codemod-able? | after the prototype |
|---|---|---|---|
| D3 state writers | 2 unparsable snippet files + 6 new writer sites | yes | 0 unparsable, 3 sites (`gems/rose_quartz/burst.py:47`, `scripts/foreman.py:193,196`) |
| D1 gems → core | 18 (10 allowlist line drift + 8 new imports) | no | — |
| D2 core → gems | 20 | no | — |
| D2-hard new layers | 14 (all `core/loop`) | no | — |

- **D3 state writers: codemod-able.** Two new refactor strategies:
  - `dedent_snippet` fixes the two unparsable snippet files.
  - `state_writer` rewrites `P.write_text(json.dumps(X[, indent=2]), encoding="utf-8")` to the sanctioned
    `core.spine.state_io.write_json(P, X)`.
  - 9/9 attempts were kept with 0 regressions; the outputs are byte-identical JSON.
  - `gems/` is excluded because D1 forbids `core.spine` in gems. The remaining 3 sites are that gem plus 2 foreman writes
    that don't match the pattern.
  - The host runs this as the `state_writer` / `dedent_snippet` arms of the refactor kind. The codemods are not applied in
    this branch, so the host earns the kept edits.
- **D1 gems → core: not codemod-able.**
  - The 10 line-drift entries are test-side re-pins, and tests are protected from the host.
  - The 8 new imports are architectural: clear_quartz→multifile/repo_oracle, fabricate→tool_reconcile/patterns,
    router→model_select/model_router, planner→memory_bus/fix_dag.
  - Plan (human): inject these as constructor arguments from `core/` (gems get callables, not imports), or move the pure
    helpers into `core.schemas`/`core.vectors`.
- **D2 core → gems / D2-hard new layers: not codemod-able.** Plan (human): one registry lookup (`GemRegistry.get(name)`)
  replacing the direct gem imports, then re-pin. Not something the gate can judge in one edit.
- `test_new_modules_importable` fails because `loop_runner_enabled()` returns True on the box. That is an environment
  default, not topology.

The topology tests stay failing (5 tests). They are dropped as `too_many_sites` rather than wrongly targeted.

## 4. Re-audit: what else blocks learning once pushed

| # | issue | status |
|---|---|---|
| 1 | **Stale bytecode in the gate.** CPython validates a `.pyc` by source mtime (whole seconds) and size. When a revert is followed by a same-size rewrite in the same second, the gate tests the *old* code (this was the batch-5 `new_module` flake). | fixed: `drop_recent_bytecode()` at the start of `run_pytest` (~4 ms); test verified to fail without it |
| 2 | **The no_context bandit arm hid the span window**, so span goals were unanswerable under that arm (1 in 5 arm draws). | fixed; regression test added |
| 3 | Span prompts were rejected as "spoilers" (the window repeats file text). | fixed: `goal_quality.spoiled` skips marker lines and `...` |
| 4 | Host has no `learning_summary.json`. | old code; written by batch-4+ code after push |
| 5 | `plan_error=ImportError`, `sota: queue empty` on the host. | old code; batch 2–5 seed + goal source fix it after push (dry-run below) |
| 6 | 141–173 artifact commits/h by the host (publish noise). | batch 5 `ETHER_PUBLISH_MIN_S=300` caps it at ≤12/h after push |

Dry run of the real-goal path on a scratch copy (seeded index, a wrong-edit model, 3 ticks):

- 51 seeded goals;
- 10–29 s per tick;
- 0 kept (correct for wrong edits);
- the tree stayed clean.

**First-hour script** `scripts/first_hour_report.py`. It reads `artifacts/host_main.json`, `artifacts/learning_summary.json`
and `git log` from a ref (default `origin/main`, `--fetch` to fetch first, `--local` for the working tree, `--json`).
It prints:

- kept/attempt;
- revert rate;
- pass rate by goal kind;
- arm spread (pulls per arm and the largest share);
- commits/h (host_main vs other).

It reads both the old and the new artifact schema. Run it right after the push, then hourly.

## Flags

| flag | default | effect |
|---|---|---|
| `ETHER_SPAN_EDIT` | 1 | span goals for too-large targets (0 = batch-5 behaviour: drop as too_large) |
| `ETHER_REFACTOR` | 0 | refactor kind; batch 6 adds `dedent_snippet`, `state_writer` strategies |
| `ETHER_MULTI_EDIT` | 0 | unchanged (batch 5) |
| `ETHER_SBFL_RANK` | b5 | unchanged (batch 5) |

## Remaining gaps (ranked)

1. **Push batches 2–6.** The host still runs old code, so nothing learns. Everything here is unmeasured on the host until then.
2. **First host hour.** Run `first_hour_report.py --fetch`. Targets:
   - kept/attempt > 0;
   - revert rate ≤ 0.8;
   - no arm > 0.6 share;
   - ≤ 12 commits/h.
3. **Topology D1/D2 architecture refactor** (human-led, plan in §3). There are 52 sites, outside the host's reach by design.
4. **The 2 real gem bugs are mistargeted.** SBFL points at shared helpers (schemas/model_select). Next: when an error
   envelope names an exception (`KeyError`, empty content), anchor on the handler that produced it.
5. **20 surviving gem mutants** (RoseQuartz 8, Selenite 4, ClearQuartz 3, others 5). They need contract tests for those
   branches (rows in `gem_mutation6.json`).
6. **8 source-text asserts.** These tests grep source, so a refactor breaks them. Rewrite them as behaviour tests (human).
7. **Env-dependent dashboard tests (2).** They need docker or curriculum data; mark them as env-gated (human decision).
8. **Host-target accuracy 0.56 on handler bugs.** RoseQuartz/Citrine are low because SBFL prefers helpers. Next step:
   per-handler span anchoring on the handler's own branch.

## Next measured steps

1. Push, then run `first_hour_report.py` at +1 h and +6 h. Record kept/attempt, revert rate and pass by kind (fix_test
   span vs function vs assign).
2. Span goals vs function goals: compare their kept rate on the host over the first 50 attempts each.
3. Enable `ETHER_REFACTOR=1` for one hour and count kept `state_writer` edits. The expected D3 sites are 3–6.
4. Re-run `gem_mutation6.py` after the host's first kept handler fix.
