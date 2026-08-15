# What we found — a handoff for Carlos

Two days of auditing and measurement, 2026-07-27 to 2026-07-29. Written so you
do not have to re-derive any of it, and so the mistakes are cheap for you
instead of expensive.

The short version: **the infrastructure you built is sound, the measurements it
was producing were not, and once they were fixed the pipeline turned out not to
beat a bare model.** That is a real result, it is now reproducible, and it says
where to build next.

---

## 1. The headline number

Four benchmarks, ~1,500 generations, two models. Both point the same way.

| model | bare | bare+sys | ether |
|---|---|---|---|
| `qwen3.6:35b-a3b` | 0.933 | — | 0.874 |
| `qwen2.5:3b` | 0.317 | 0.333 | **0.292** |

`ether − bare+sys = −0.042`, McNemar p = 0.22, 360 samples, zero leaks.

**There is no evidence the current pipeline improves generated code.** It is
neutral-to-slightly-negative at both ends of the model size range.

Full data: `docs/results/ablation_qwen2.5-3b_clean.json`.

### The number we retracted

An earlier run reported `ether 0.875` vs `bare 0.275` — **+53pp, p = 0.00002**.
It was committed and then retracted the same night. It was contamination
(§2, channel 7). Removing the leak did not shrink the effect; it erased it and
flipped the sign. If you see that number anywhere, it is void.

---

## 2. Seven leak channels

Every one of these put the answer, or the test, into the model's prompt. Six of
the seven were found **after** declaring the previous one fixed.

| # | channel | how it leaked |
|---|---|---|
| 1 | curriculum objectives | contained the implementation AND its assertions |
| 2 | bench prompts | assertions inline in the objective |
| 3 | `hidden_quiz.py` | private grader copy with no leak check at all |
| 4 | BM25 retrieval | indexed `scripts/`, which holds `bench.py` and its holdouts |
| 5 | `success_patterns.jsonl` | leaked-era artifacts replayed as few-shot examples |
| 6 | `experience/pass.jsonl` | same, via a second store |
| 7 | **solution identity** | retrieval served a prior *correct solution* to the task under test |

Channel 7 is the important one, because it is not about tests at all. The
holdout never appeared in the prompt — the **solution** did — so the assertion
guard read `leaked = 0`, truthfully and uselessly.

> **Few-shot retrieval over a store that accumulates solved benchmark tasks is
> STRUCTURALLY a leak.** Not a bug to patch once: any similarity search will
> find the answer if the answer is in the corpus.

This matters directly for the self-improving flywheel. A loop that saves its
successes and retrieves them later will always contaminate its own evaluation
unless the store excludes the task under test. That is now enforced in both
retrieval paths (`core/experience.py`, `tools/persistent/few_shot_pack.py`),
failing closed — if the check cannot run, it serves nothing.

**Defence:** `core/prompt_guard.py` inspects the finished prompt rather than
maintaining a list of known channels. That is the only reason 5, 6 and 7 were
caught.

---

## 3. Verification was theatre

Before this work, `confidence` measured *"the process exited 0"*. Verified by
execution — all of these scored **1.000**:

- `def solve(n): pass` — no assertions at all
- an assertion inside a **comment**
- a **false** assertion swallowed by `except AssertionError`
- `print("42 passed in 0.01s")` — forged test output
- assertions under `if False:`
- assertions in a function nothing calls

Meanwhile honest code that reported a real failure scored **0.26**. The metric
actively rewarded concealment, and it fed the bandit reward, the curriculum
tier and the flywheel commit gate.

Now: `core/assert_audit.py` counts only assertions that could actually fail
(AST-parsed, no tautologies, no dead branches, no swallowed failures, no
unreachable functions), and `core/holdout.py` grades against assertions the
generator never saw, with an unpredictable sentinel so `sys.exit(0)` cannot
fake a pass.

**Every `conf=1.000` in the git history predating this work is meaningless.**

---

## 4. Things that were silently broken

Each of these looked fine and did nothing:

- **`ETHER_SANDBOX_BACKEND=docker` ran code on the host** when docker was
  missing, with empty `security_flags`. Now fails closed.
- **The model ran at `presence_penalty=1.5`, `temperature=1.0`** — the
  Modelfile defaults, because the router only ever sent `num_predict`. A
  presence penalty punishes repeating tokens; correct code *must* repeat
  identifiers. Close to worst-case sampling for code, for the project's
  entire life.
- **`num_predict=4096` on a reasoning model.** Thinking tokens ate the budget:
  one 360-sample run had **214 failures** (147 timeouts, 64 empty completions).
  `think` is now explicit and off by default for code.
- **Three safety flags did not gate what they named.** `ETHER_FLYWHEEL_PUSH=0`
  still pushed (hardcoded `do_push=True` into a `do_push or env` expression);
  `ETHER_AUTO_PROMOTE=0` still promoted (`reconcile()` had no gate);
  `ETHER_AUTO_MODEL` overwrote an explicit model choice from a *read-only
  dashboard probe*, at one point selecting an embedding model as the coder.
  All nine flags are now pinned by `tests/test_safety_flags.py`.
- **`promote()`'s regex had `{{8}}` in a non-f-string**, so promoted tools kept
  their timestamp suffix and `resolve_tool()` could never find them.
  Fabricate → promote → reuse never worked.
- **The bench guardian ratcheted its own baseline down** — 0.95 → 0.41 without
  ever freezing, each step "within tolerance".
- **`pytest` mutated production state**: fake rewards into the live bandit,
  mock runs into the few-shot store (84 of 101 rows were `write hello`
  artifacts served to the model as worked examples), and it promoted the real
  curriculum tier 0 → 3.

---

## 5. Why the repair loop contributes nothing

Measured: `ether` vs `ether-no-repair` came back **bit-identical** — 105/120
each, zero discordant pairs, p = 1.0.

The cause: **repair only fires when the sandbox exits non-zero.** A wrong
answer usually runs fine, so repair never engages. Every bare-arm failure in
the clean run was `holdout assertions failed`, not a crash.

That null result is what exposed leak channel 7 — repair cannot matter when the
answer is already in the prompt. **The arm that showed nothing found the
contamination the arm that showed +53 concealed.**

---

## 6. Difficulty is bimodal, and cannot be aimed at

78 candidate tasks, gated and measured against the bare 35B:

```
0/3  17 tasks   floor
1/3   6 tasks   informative
2/3   9 tasks   informative
3/3  46 tasks   ceiling
```

Only **15 of 78 (19%)** land where a scaffold could show anything. Round 1,
written blind, yielded 22% mid-band. Round 2, written *deliberately* at the
middle, yielded **7%** — aiming made it worse. Harder objectives jump from
ceiling straight to floor.

Consequence: a strong model has almost no headroom on single-file stdlib tasks,
which is why three benchmarks returned null before we understood why. Test
small models, or test harder *kinds* of task (multi-file, editing existing
code) rather than harder instances of the same kind.

---

## 7. What is worth keeping

The apparatus, which is genuinely good:

- **`core/holdout.py`** — grades against unseen assertions, strips the model's
  own asserts so they cannot preempt, requires a sentinel so a clean exit
  cannot fake a pass. Mutation score 0.966 over 1,689 mutants.
- **`core/prompt_guard.py`** — catches leaks by inspecting the prompt, not by
  remembering channels.
- **`core/assert_audit.py`** — honest assertion counting.
- **`scripts/ablation.py`** — three arms, seeded, resumable, aborts at >25%
  errors, records model digest and decode settings, clustered bootstrap CI plus
  paired McNemar, prints the minimum detectable effect *before* running.
- **`scripts/build_headroom.py` / `build_calibrated.py`** — suites that refuse
  to ship a task unless a reference implementation passes it and mutants fail
  it.
- 658 tests, up from 48.

---

## 8. What has never been tried

The pipeline has never had:

- **best-of-N with verifier selection** (`pass@5 ≫ pass@1` on a small model)
- **static analysis in the loop** — ruff/mypy work on tasks with *no* holdout,
  which is every real task
- **a repair prompt showing the code that actually ran** (it currently shows
  the original beside a traceback from the harnessed version — line numbers
  that refer to a file the model never saw)
- **an agent loop that iterates more than once**, chooses its own actions, or
  edits existing files

So the negative result says *this implementation* does not help. It does not
say the idea is wrong. Those four mechanisms are the ones with published
evidence behind them, and none of them are in here yet.

---

## 9. Operational notes

- `memory/` is gitignored, so benchmark datasets are **local artifacts**. Tests
  that read them must `skip`, never fail — `pytest` is a static gate in the
  flywheel, so one unguarded test drops a whole machine out of the loop. That
  happened to your Windows box twice.
- `ETHER_WARM_SANDBOX` stays **off**. It shares `/tmp` across programs; one
  program was verified planting `sitecustomize.py` that a later, unrelated
  program executed. It buys 0.67% of a run.
- Run `scripts/build_headroom.py` and `build_calibrated.py` after cloning, or
  the benchmark tests skip.
- Baselines are per bench mode now — `--fast` (5 easy tasks) cannot re-pin the
  full bench's bar.

---

## 10. The one habit worth adopting

Every impressive number in this project so far has been contamination, and
every one was found by a **mechanical check at the point of use** rather than
by reasoning about which channels exist. Reasoning found none of them; the
guard found five.

When you next see a result that looks great, the fastest way to find out if it
is real is to run the arm you expect to show *nothing*. That is what caught the
biggest one.

---

## 11. The agent loop — built, measured, does not help

`core/agent_loop.py` + `core/verifier.py`, behind `ETHER_AGENT_LOOP=1`. It works
mechanically: draws N candidates at climbing temperature, scores each without a
holdout, repairs against what actually ran, selects the best and never regresses.
Verified live selecting the best of three over two worse ones.

**It does not improve the pass rate. It makes it worse.**

| arm | rate |
|---|---|
| `bare+sys` | 0.333 |
| `ether-loop` | 0.083 |

Three defects were found and fixed along the way, each real:

1. **Best-of-N was best-of-one.** The loop early-stopped whenever the verifier
   scored above 0.95, so it drew a single candidate. An oracle-free verifier
   SATURATES — confidently wrong code parses, runs, is ruff-clean, mutates
   nothing, survives empty input, and scores 1.000. Early stopping is now
   opt-in.
2. **The loop instructed the model to violate the spec.** Its prompt said
   "handle empty input without raising" and "do not mutate the caller's
   arguments". **21 of 40 headroom tasks are GRADED ON RAISING**, and 20 mention
   in-place modification. Generic good-practice advice is not free.
3. The verifier scored a deliberate `ValueError` on empty input as correct but
   treated `KeyError`/`IndexError` as a crash. Broadening it was WRONG —
   `return items[0]` raising IndexError is accidental, not deliberate.
   Distinguishing them needs the spec, not the exception type. Left as-is.

None of it closed the gap.

### The measurement that explains why

Oracle pass@3 is the ceiling ANY selector could reach — the fraction of tasks
where at least one of three samples passed:

| arm | pass@1 | oracle pass@3 | headroom |
|---|---|---|---|
| `bare` | 0.275 | 0.400 | +0.125 |
| `bare+sys` | 0.342 | 0.400 | **+0.058** |

**A perfect, infallible selector could gain 5.8 points.** Best-of-N requires
pass@N >> pass@1; here the gap is 5.8pp and a saturating verifier captures a
fraction of it at ~7x the cost.

Observed directly on hr03: four candidates, **all scored 1.000, all failed the
holdout**, consistency 0.583 — they agreed because they were identically wrong.
Temperature varies the phrasing, not the model's understanding.

### What this means for whoever picks this up

The bottleneck is the model's understanding, not the sampling, the prompt, or
the selection. That is now four independent measurements agreeing.

Do not spend time optimising the selector. Its ceiling is measured and it is
5.8 points.

The asymmetry worth building on: this system is far better at saying **"this is
wrong"** than at producing something right. The verifier could not rank the four
candidates, but the holdout rejected all four correctly. Point that at repo
tasks — where the bare model scores near zero and the repository's own test
suite is a real oracle that cannot be leaked into a prompt because it is run,
not shown.

---

## 12. Phase D — tool path on hard repo-oracle pack (2026-08-01)

### Setup

- Host: GTX 1650 4GB / 12GB, `ETHER_PRIMARY_MODEL=qwen3.5:4b`
- Pack: lru, merge, ledger, topo, intervals (project pytest oracle)
- Arms: **direct** (ToolRuntime), **pipeline** (Pipeline + tools + same-workspace verify), **bare** (Pipeline tools off)
- Runner: `scripts/batch_phase_d.py` (must `load_dotenv`; must pass `--max-steps`)

### Result

| arm | pass/5 |
|-----|--------|
| direct | 5/5 |
| pipeline (max_steps=16) | 5/5 |
| bare | 0/5 |

Pipeline under wrong config looked worse: with Rose default `qwen2.5-coder:3b` and 12 steps, pipeline was **3/5** (ledger/topo `max_steps`). Same fixtures **5/5** once model and step budget matched host intent.

### What this does and does not overturn

- Does **not** overturn §1 holdout generate ablation (ether ≤ bare+sys).
- Does show the **repo-grounded** direction from §8/§11 is real: tools + project tests beat one-shot generate on this pack.
- Best-of-N agent loop (§11) stays off — different mechanism, already net negative on holdout.

### Product implications

1. Default product path for fix-tasks: tool runtime ON, Clear Quartz re-verify on the tool workspace (not generate-first).
2. Always print/resolve `ETHER_PRIMARY_MODEL` in measure scripts; silent 3b fallback wasted a day of matrix noise.
3. Keep curriculum / bandit / flywheel off until a measurement on this task class says otherwise.

---

## 13. Phase E — mutation restore (2026-08-01)

Host `qwen3.5:4b`. Six named mutations applied to `_fixed_solutions`, oracle = project pytest.

| arm | pass/6 |
|-----|--------|
| direct scripted | 6/6 |
| direct live | **3/6** |
| bare live | **1/6** |

Direct live PASS: `lru_no_evict`, `merge_drop_b_tail`, `intervals_no_sort`.  
Direct live FAIL (max_steps): both ledger mutations, `topo_drop_cycle_raise` (score 0.571).  
Bare live PASS only: `topo_drop_cycle_raise`.

### Implications

1. Phase D 5/5 does **not** automatically transfer to regression-style mutations — ledger/topo need more budget or stronger tool prompts.
2. Tools still outperform bare on this pack (3/6 vs 1/6); bare is not competitive on lru/merge/intervals.
3. Next evidence-ranked step remains **real external repos** (TASKS #1), not selector polish.

---

## 14. 148× latency gap + quant / vLLM (2026-08-15)

Measured on host (GTX 1650 4GB, `qwen3.5:4b`):

| path | elapsed | result |
|------|---------|--------|
| pipeline scripted (ledger) | 2.142 s | PASS |
| pipeline live (ledger) | 317.817 s | FAIL (tool_runtime timeout) |
| ratio | **148.4×** | |

Root cause is not quant alone. Scripted is deterministic tool path; live pays full multi-step LLM inference + KV + orchestration on Turing bandwidth. Direct hard pack mean is already ~2.4 s (5/5).

**Quantization:** Q4_K_M (or Q4_0) is the only viable point. Q5+ / FP16 does not fit 4 GB without offload. Quality loss is real but secondary to step count.

**vLLM:** Investigated and **rejected as primary path** for this host. Reasons: Windows (no official support), 4 GB below comfortable operating point, FlashAttention-2 needs SM ≥ 8.0, continuous-batching advantage is small for short agent tool loops. Keep Ollama. Revisit only on cousin hardware or after WSL2 + measured TTFT/tok/s A/B.

**Policy locked:** FAST-first + live purge (`live_skip_ticks=36`, kill_live first). Latency mitigation checklist in `artifacts/performance_benchmark.json` and `docs/models.md`. Phase 1D (honest live tool path) remains the gate; do not re-introduce live into steady until it is measured green.
