# COWORK — what changed, 2026-07-27 to 2026-07-29

A record of the work itself. **`docs/FINDINGS.md` is the companion** and covers
*what we learned*; this covers *what we touched*, so you can find things and
know what not to re-do.

Scope: commits `c9773cb..938d44c`. **98 files, +27,874 / −915.** Tests 48 → 763.

Everything is on `main` and pushed.

---

## The arc, in one paragraph

We set out to make ETHER better and spent most of the time discovering that its
measurements were not real. Seven separate channels were putting the answer or
the test into the model's prompt; verification counted assertions that could not
fail; several safety flags gated nothing. Once those were closed and the
benchmarks rebuilt, the honest measurement came back: **the pipeline does not
beat a bare model.** We then built the agent loop that had never existed, and
measured that it does not help either — and why. Full detail in `FINDINGS.md`.

---

## 1. Verification — was theatre, now real

**New:** `core/assert_audit.py`, `core/holdout.py`, `core/prompt_guard.py`

The old `confidence` measured "the process exited 0". A no-op function, an
assert inside a comment, a false assert swallowed by `except`, and a printed
`"42 passed"` all scored **1.000**, while honest code reporting a failure scored
0.26.

- `assert_audit.count_real_asserts` — AST-based. Skips tautologies, dead
  branches, swallowed failures, and assertions in functions nothing calls.
- `holdout.grade_against_holdout` — grades against assertions the generator
  never saw. Strips the model's own module-level asserts so they cannot preempt,
  and emits an unpredictable sentinel so `sys.exit(0)` cannot fake a pass.
- `prompt_guard` — inspects the finished prompt rather than maintaining a list
  of known leak channels. This is what caught channels 5, 6 and 7.
- `core/confidence.py` — untested ceiling 0.70 → 0.65, so unverified code cannot
  clear a 0.70 gate.

## 2. Leak channels — seven, all closed

`core/curriculum.py`, `scripts/bench.py`, `scripts/hidden_quiz.py`,
`core/rag_bm25.py`, `core/experience.py`, `tools/persistent/few_shot_pack.py`,
`tools/persistent/save_success_pattern.py`

Curriculum objectives contained their own answers; bench prompts had assertions
inline; `hidden_quiz` had a private grader with no check; BM25 indexed
`scripts/`, which holds the holdouts; two memory stores replayed leaked-era
artifacts as few-shot examples; and **retrieval served prior correct solutions
to the task under test**.

That last one is structural, not a bug — any similarity search will find the
answer if the answer is in the corpus. Both retrieval paths now drop examples
that define a symbol the objective asks for, failing closed.

## 3. Sandbox and security

`gems/clear_quartz/sandbox.py`, `gems/clear_quartz/warm.py`,
`gems/grandidierite/registry.py`, `gems/black_tourmaline/security.py`,
`core/patch_loop.py`, `core/tool_reconcile.py`

- `ETHER_SANDBOX_BACKEND=docker` silently ran code **on the host** when Docker
  was missing, with empty `security_flags`. Now fails closed.
- Container hardened: `--user 65534`, `--read-only`, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, `--pids-limit`, tmpfs `/tmp`. Verified in
  container: uid 65534, `CapEff 0000000000000000`.
- `patch_loop` path containment was a substring test for `"memory/scratch"` that
  a trailing tab comment and git rename headers both bypassed, while `git apply`
  ran at repo root. Now resolves every path including rename targets; opt-in via
  `ETHER_PATCH_LOOP=1`.
- `resolve_tool` no longer executes from `tools/quarantine/`.
- The audit gate rejects on **any** violation, not `risk < 0.5` — `os.system`
  and `subprocess.run` were being auto-approved.
- Warm container hardened and left off; it shares `/tmp` across programs and one
  program was verified planting `sitecustomize.py` that a later, unrelated
  program executed.

## 4. Safety flags — three gated nothing

`scripts/ether_daemon.py`, `scripts/run_smart_cycle.py`,
`scripts/desktop_runtime.py`, `core/model_select.py`, **`tests/test_safety_flags.py`**

- `ETHER_FLYWHEEL_PUSH=0` still pushed — `run_smart_cycle` passed a hardcoded
  `do_push=True` into a `do_push or env` expression, and the launchers called
  `os.environ.setdefault` *before* `load_dotenv`.
- `ETHER_AUTO_PROMOTE=0` still promoted — `reconcile()` had no gate at all.
- `ETHER_AUTO_MODEL` overwrote an explicit model choice from a **read-only
  dashboard probe**, at one point selecting an embedding model as the coder.

All nine flags are now pinned by tests, two of them structurally (source
inspection), because the defects were in *how a caller was wired*, not in the
flag's value.

## 5. Model configuration

`gems/rose_quartz/router.py`, `core/schemas.py`

- Only `num_predict` was ever sent, so Ollama used Modelfile defaults:
  `temperature=1.0` and **`presence_penalty=1.5`**. A presence penalty punishes
  repeating tokens; correct code *must* repeat identifiers. Close to worst-case
  sampling for code, for the project's entire life.
- `think` is now explicit and **off by default**. Reasoning tokens ate
  `num_predict=4096`: one 360-sample run had **214 failures** (147 timeouts, 64
  empty completions).
- Empty completions are now an error rather than a success envelope.
- `RoseQuartzRequest` gained optional `temperature`/`seed`; these were
  environment-only, which made per-attempt sampling impossible.

## 6. Benchmarks and measurement

**New:** `scripts/ablation.py`, `scripts/build_headroom.py`,
`scripts/build_calibrated.py`, `docs/results/*.json`

- **`ablation.py`** — three arms (`bare`, `bare+sys`, `ether`) plus
  `ether-no-retrieval`, `ether-no-repair`, `ether-loop`. Seeded, resumable,
  records model digest and decode settings, clustered bootstrap CI, paired
  McNemar, prints its own minimum detectable effect *before* running, aborts at
  >25% errors, excludes leaked samples from denominators.
- **Suites** refuse to ship a task unless a reference implementation passes it
  **and** mutants fail it (≥0.90 mutation score). That gate caught two tasks
  that were mathematically impossible to pass.
- `--bare-strip-preamble` exists because every objective opens with "Write only
  Python" — without it, `bare` vs `bare+sys` measures turn *placement*, not the
  instruction.

## 7. Health, guardian, learning

`core/bench_guardian.py`, `core/health_metric.py`, `core/autonomy.py`,
`core/learning.py`, `core/pipeline.py`, `core/experience.py`

- The guardian **ratcheted its own baseline down** — 0.95 → 0.41 without ever
  freezing. Now ratchets up only; lowering requires an explicit operator call.
  Baselines are **per bench mode**, so `--fast` (5 easy tasks) cannot re-pin the
  full bench's bar.
- `declare_healthy()` gated nothing — the daemon logged the verdict and ran
  anyway. It now skips.
- Bandit: 10 arms → 6 real mechanisms (`rag_on`, `few_shot_on`, `burst_on_fail`
  were verified no-ops), per-context statistics, `fail_kind` re-draw at retry,
  and the double-update from two stale in-memory copies removed.
- Experience vault deduplicated and infra-filtered — 13 of 22 "success
  examples" were the same stub, and **all 26 "failures" were infrastructure
  outages**, not code defects.

## 8. Pipeline correctness

`core/pipeline.py`, `cli/main.py`, `core/registry.py`, `core/multifile.py`

- `ether run` **exited 0 when the generated code never ran** — status was
  asserted, not derived. Scripting `ether run … && deploy` was unsafe.
- `registry.py` imported a symbol that never existed, raising `ImportError` into
  a bare `except` on every registry build and leaving four modules dead.
- An audit-gem outage was read as a *rejection*, so the bandit was penalised
  −0.2 for code that was fine.
- `multifile` emitted a runner pointing at a **host** path the container cannot
  see, so every multifile run died with `FileNotFoundError`.
- `RUNS_DIR` is repo-root anchored; it was CWD-relative, so runs started
  elsewhere vanished from the dashboard.

## 9. The agent loop

**New:** `core/agent_loop.py`, `core/verifier.py`

Built, wired behind `ETHER_AGENT_LOOP=1`, measured. Draws N candidates at
climbing temperature, scores each without a holdout, repairs against what
actually ran, selects the best, never regresses.

**It does not help** — 0.083 vs `bare+sys` 0.333. See `FINDINGS.md` §11 for the
three defects found in it and the oracle pass@3 measurement that explains why
fixing them did not matter.

## 10. Test infrastructure

`tests/conftest.py` and 15 new test files

`pytest` was **mutating production state**: fake rewards into the live bandit,
mock runs into the few-shot store that were then served to the model as worked
examples, and it promoted the real curriculum tier 0 → 3. Now isolated, with the
RNG seeded per test after two bandit tests were found failing ~1 run in 4.

---

## Things that will bite you

- **`memory/` is gitignored.** Benchmark datasets are local artifacts. Run
  `scripts/build_headroom.py` and `scripts/build_calibrated.py` after cloning.
  Tests that read them **skip**, never fail — one unguarded test took the
  Windows box out of the flywheel twice.
- **A red `main` kills the other machine.** `pytest` is a static gate in the
  flywheel. Use `pytest && git push` as one command. This bit us three times.
- **The flywheel is a third writer.** It commits and pushes to `main` on a
  timer, twice landing between a `fetch` and a `push`. Set
  `ETHER_FLYWHEEL_PUSH=0` on both machines while collaborating.
- **`ETHER_WARM_SANDBOX` stays off.** It buys 0.67% of a run and shares `/tmp`
  across programs.
- **Every `conf=1.000` predating this work is meaningless**, and the `+53pp`
  result committed on 2026-07-29 was retracted the same night.
