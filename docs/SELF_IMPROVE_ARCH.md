# Self-improving agent architectures for ETHER — study + roadmap (2026-11-21, branch ether-batch7)

Base: `ether-batch6` @ `c5148abe93` (batches 2–6, not on origin/main; the live host still runs old code).
File:line references below are to that base unless marked **b7**. Research and design only; the one
prototype (§6) is flag-gated **off**. Nothing is pushed.

Doctrine held throughout: single writer (`scripts/host_main.py`), Matrix read-only, tool-first, honest gate
only (a tool edit + the target test passing + 0 regressions + sibling tests passing; generate-only is never a
PASS), GTX 1650 4 GB + `qwen3.5:4b`, one model, one request at a time, no second installer, every new
behaviour behind a flag.

---------------------------------------------------------------------------------------------------------

## 1. Inventory: what actually self-improves today

| Surface | Where | Live on the host after the 2–6 push? | What it learns from | Verdict |
|---|---|---|---|---|
| **Honest gate** | `core/agent/sota.py:403` `_attempt_real` → `goal_source.gate` (`sota.py:491`, `goal_source.py:1252`); revert at `sota.py:502` | yes | pytest on target + siblings + guard suite | the only reward; solid |
| **Goal source** (failing tests, lint, SBFL b5, span goals) | `core/agent/goal_source.py:882` `next_real`, `MAX_TARGET_TRIES=6` at `:879`; seed `config/goal_seed.json` (56 fix_test + 4 lint) | yes | repo state | **finite**: 60 goals × ≤6 tries ≈ 360 attempt slots, then the pool is empty until the code changes (§3, gap G1) |
| **Bandit** (Thompson, 5 arms, per goal kind/bucket) | `core/agent/bandit.py:41` `REAL_ARMS`, `:344` `choose`, `:300` `tries_for`; called from `outcome.py:141` `choose` / `:273` `record` | yes (`ETHER_BANDIT=thompson`) | `reward01` from the gate; logs propensity | the one learned policy; 5 arms are all prompt/context variants of one call |
| **Promotion** | `outcome.py:368` `maybe_promote`, `bandit.py:55` `PROMOTE_PROB=0.9`, `MIN_PASSES=3` (`outcome.py:26`) | yes (`ETHER_PROMOTE_RULE=posterior`) | posterior P(arm beats incumbent) | sound gate; never changes code |
| **Trajectories** | `outcome.py:43` → `memory/learning/trajectories.jsonl` (cap 2000), fields at `outcome.py:276-299` | yes | every attempt | logs `arm, propensity, reward01, secs, via, reply_tail[-160:]` — **not** the kept diff, so nothing can be retrieved from it |
| **(1+λ)-ES** over arm logits | `core/agent/evolve_es.py:1-30`, hook `outcome.py:318` | no (`ETHER_NEURO_ES=0`) | SNIPS replay of trajectories | correct to keep off (NEUROEVOLUTION.md: gate precision <50% at 300+ attempts) |
| **learn.py ladder** | `core/agent/learn.py:10` `LADDER`, `:36` `next_from`; `sota.py:227` `legacy_allowed` | **retired** (goal guard on; `ETHER_SOTA_LEGACY=1` revives it) | which ladder functions were kept | fixed curriculum of spoiled/constant goals; no learning left in it |
| **Gem bag** (`chain`) | `core/agent/gems.py:99` | only when the model emits a tool call inside `react` (`core/agent/react.py:15`) | nothing | 5 hard-coded string rules (`"subprocess" in text`, `text.startswith("def ")`, `'"tool"' in text`, skill-name lookup); no state, no learned decision |
| **"Citrine" stage of the bag** | `gems.py:49` `memory` → `sota.remember` (`sota.py:327`) | as above | — | writes one line to `artifacts/sota.json["lessons"]` (cap **8**). Real-goal prompts never read it (`goal_source.build_prompt`, `goal_source.py:952-1003`, has no memory input) |
| **Citrine / Qdrant** | `gems/citrine/memory.py:31-39` collections `ether_code, patterns, failures, runs`; write `core/patterns.py:31` `index_pass_pattern` from `core/loop/handlers/finalize.py:136` and `gems/grandidierite/fabricate.py:244`; read `core/patterns.py:119` via `core/experience.py:218,289` | **not on the real-goal path** | legacy pipeline passes | retrieval feeds `core/loop/generate_retry_loop.py:93-94` (legacy generate pipeline / FIFO jobs). Degrades to BM25 when Qdrant is down (`core/rag_bm25.py`). The honest real-goal loop uses **no memory at all** |
| **Experience vault** (`memory/experience/pass.jsonl`) | `core/experience.py:71` `record`, `:218` `retrieve` | legacy path only | verified legacy passes | same: unused by the real-goal loop. `ArmBehaviour.use_few_shot/use_experience` (`core/learning.py:24-25`) are **ignored** by `build_prompt` |
| **Evolution pipeline** (fabricate → quarantine → promote) | `scripts/ether_evolve.py:116` `cycle`; `fabricate.py:259`, stub-only at `:264`, `ETHER_AUTO_PROMOTE` at `:263/:330`; `core/tool_reconcile.py:23-38` `_promotion_gate` | **not live on the 1650**: `cycle()` is only called in the non-Windows branch of `host_main._tick` (`scripts/host_main.py:186` vs `:281-285`); on Windows it never runs. Where it runs it is stub-only and `ETHER_AUTO_PROMOTE=0` | sandbox self-test, static safety, audit | its gate is *not* the honest gate (no target test from the repo), so it must not feed learning as is |
| **LoRA** | `core/lora_train.py:44` (training wheels), `core/lora_prep.py` | no (`ETHER_LORA_TRAIN=0`) | — | infeasible on the host (§4, option 14) |
| **Sampling** | `scripts/host_main.py:145-146` `_code` → `scripts/live_edit_tx.py:27,38` `_ask(..., temperature=0)` | yes | — | **every real-goal reply is greedy (T=0)**. A retry with the same arm and prompt returns (near-)the same reply, so most of the 6 tries per goal can be wasted (gap G2) |

**Bottom line.** After the push, ETHER learns exactly one thing: which of 5 prompt variants to use, per goal kind,
from 0/1 gate outcomes. Memory, skills, evolution and the gem bag do not touch the real-goal loop. The two
structural limits are a **finite goal pool** (G1) and **greedy decoding** that makes retries near-duplicates (G2).
The third is that **a kept edit is forgotten**: nothing from a pass is ever shown to the model again (G3).

## 2. Cost model on the 1650 (planning numbers; Phase 0 replaces them)

- VRAM: 2,710 / 4,096 MB used with the 4B loaded (`artifacts/gpu_metrics.json`, 2026-09-12) → ~1.4 GB free; no room for a second model or GPU training while inference is up. Host RAM 12 GB (`config/hardware_profile.json`).
- One attempt = guard pytest before + 1 model call (prompt ≤ 5,732 chars at 4K ctx, reply cap 240–768 tokens) + gate pytest after. The bandit's prior is 45 s (`bandit.py:53`). The only measured live latency is the old multi-step pipeline: p50 136 s, p95 178 s completed (`artifacts/latency_slo.json`, n=246). Planning range **20–90 s per attempt**, of which **~15–55 GPU-s** is the model; **~40–120 attempts/hour**, central 60/h. The trajectories log `secs` per attempt, so Phase 0 gives the real figure.
- Pool: 360 attempt slots ⇒ at 60/h the current pool is used up in **~6 h** (range 3–9 h) unless new failing tests appear. Every A/B below competes for those slots.

## 3. Gaps that decide the ranking

- **G1 finite curriculum.** No source of new goals once the 60 are kept or dropped. Voyager's automatic curriculum, SWE-smith and Self-play SWE-RL all hinge on an endless supply of verifiable tasks.
- **G2 greedy retries.** T=0 everywhere; `tries_for` gives ≤2 tries per attempt and the goal gets ≤6 attempts, mostly with identical prompts. Repeated sampling is the single biggest test-time lever in the literature (SWE-bench Lite 15.9 % → 56 % with 250 samples, Large Language Monkeys) but needs diversity.
- **G3 no episodic memory on the real path.** Kept edits are not stored or retrieved (ExpeL, AWM, Voyager all show this is where cheap gains are).
- **G4 learned policy is tiny.** 5 near-identical prompt arms; context features (via, error kind, tractability) exist (`bandit.py:57`) but only LinUCB uses them and it's optional.
- **G5 no safe path for self-modification.** `core/agent/` is protected from host edits (`goal_quality.py:17`), which is right; there is no archive/holdout mechanism for *data-level* policy changes either.
- Found during the replay: 2 seed goals on `Pipeline.__init__` are rejected as spoiler by the base prompt itself (the test shows another `def __init__`), so they burn without an attempt. Small, but a real false positive in `goal_quality.spoiled`.

## 4. Options evaluated

Numbers: **GPU-s** = extra model seconds per attempt vs today; **gain** = literature result (source) → our *estimate* for a 4B on ETHER's goals (an estimate, to be replaced by the A/B); **hack risk** = how easily it could raise reward without real fixes, given the gate.

| # | Option | GPU-s / attempt | VRAM / RAM | Honest-gate fit | Gain: literature → ETHER estimate | Hack risk | Integration point | Flag | Primary metric |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Kept-edit exemplar retrieval** (ExpeL, AWM, Voyager-style retrieval of verified solutions) | +0 calls; +~100 prompt tokens (block median 400 chars) ≈ +0.3–0.6 s prefill | 0 / <1 MB | store holds only gate keeps; leak rules; spoiler guard still runs | AWM +24.6 % / +51.1 % relative success (web); ExpeL gains from insights+exemplars → **+10–30 % relative kept/attempt** on goals with a similar sibling | low | `sota._attempt_real` keep branch + `goal_source.build_prompt`; bandit arm `exemplar` | `ETHER_EXEMPLARS=0/record/1` (**prototyped**) | kept/attempt (exemplar vs default, eligible attempts only), reuse rate |
| 2 | **Try-indexed temperature + duplicate-reply skip** (repeated sampling across the goal's 6 tries) | 0 extra calls; saves a gate run per duplicate (2–20 s CPU) | 0 | gate unchanged; only decoding changes | Large Language Monkeys 15.9→56 % at 250 samples; at ≤6 samples expect **+20–50 % relative pass@6** vs greedy if Phase 0 shows many duplicate replies | low–med (more samples → more chances to pass a weak test; siblings + regressions + revert-rate watch) | `host_main._code` → `_ask(temperature=f(try))`; dedupe on `reply` hash per goal in `_attempt_real` | `ETHER_SAMPLE_TEMP` (e.g. `0,0.6,0.8`), `ETHER_DEDUP_REPLY=1` | duplicate-reply rate, pass@k by try index, kept per GPU-hour |
| 3 | **Bug-injection goals** (SWE-smith, Self-play SWE-RL; mutants from batch-6 `gem_mutation6`) | 0 model change; CPU to validate a mutant (2–20 s pytest) | scratch copy of the touched file | the bug is specified by tests that fail on the mutant and pass on HEAD → a real fail-to-pass goal | SWE-smith: 50k synthetic task instances → 40.2 % SWE-bench Verified (32B trained on them); SSR +10.4 pts → for ETHER: **removes G1** (43 caught mutants today = +72 % goals; any covered function can be mutated) | med: "revert the mutant" ≠ real bug fixing → separate goal kind `mutant`, separate bandit table, separate metrics; mutants never published; exemplars from mutants never shown to real goals | new goal kind in `goal_source` (scratch-only apply); deterministic AST mutation operators, never the model | `ETHER_MUTANT_GOALS=1` | open pool size, hours to pool exhaustion, kept/attempt by kind |
| 4 | **Best-of-n inside one attempt** (n=3, early stop at first gate pass; CodeT/Agentless-style validation) | ×1–3 model time (mean ≈ ×(1−(1−p)^n)/p) | 0 | the verifier is the real gate, picking the first passing candidate is legitimate | concentrates the same samples as #2 on one tick; same expected kept per GPU-hour when goals are similar | low–med | loop around `react` in `_attempt_real` | `ETHER_BEST_OF=3` | time-to-first-keep per goal |
| 5 | **Hierarchical / contextual bandit** (pooled Beta prior across kinds; LinUCB on existing features) | 0 | 0 | reward unchanged | BANDITS.md sim: contextual only helps if pass rates differ by goal type → small until ≥300 tries | none | `bandit.py:110` `prior`, `:248` `features` | `ETHER_BANDIT=linucb`, new `ETHER_BANDIT_HIER=1` | regret proxy: kept/attempt vs best fixed arm (off-policy, SNIPS) |
| 6 | **Reflexion-style self-reflection on retry** | +1 call (~10–25 s) per retry | 0 | reflection text is not reward; gate still decides | Reflexion 91 % pass@1 HumanEval (GPT-4); 4B reflections are weak → **0–10 %**; `repair_heavy` already feeds the failure tail back | low | `tries_for` path, feedback string in `build_prompt` | `ETHER_REFLECT=1` | kept on try 2 / try 1 |
| 7 | **Skill library of verified codemods / tool sequences** (Voyager; AWM workflows; re-wire fabricate→quarantine→promote under the honest gate) | 0 for codemods (deterministic); fabricate = +1 call per proposal | small | a skill is promoted only after ≥3 gate keeps with 0 regressions on *different* goals | Voyager 3.3× more unique items, 15.3× faster milestones → for ETHER: turns repeated fixes into tool edits that cost 0 GPU-s | med (a skill that special-cases tests would spread; require diverse goals + revert-rate check) | `core/agent/refactor.py` strategies as the first skills; `tool_reconcile._promotion_gate` gets an honest-gate requirement | `ETHER_SKILL_LIB=1` | skill reuse rate, kept per GPU-hour, % keeps that are tool-only |
| 8 | **MAP-Elites / quality-diversity over prompt programs** (descriptors: context mode × retry × exemplar on/off × goal kind) | 0 extra per attempt; needs ~20 attempts per cell | pyribs on CPU | each evaluation is a live gate attempt | QD keeps diverse working strategies; with 18 cells × 20 = 360 attempts it costs **one whole pool** per sweep → only after #3 | low | generalises `ETHER_BANDIT_FACTORED` (`bandit.py:262`) | `ETHER_QD=1` | cells filled, best-cell kept/attempt, arm entropy |
| 9 | **(1+λ)-ES / neuroevolution** | 0 | CPU 8–36 ms per fit | offline SNIPS | NEUROEVOLUTION.md: no better than the bandit on 21 params; gate precision <50 % | none | `evolve_es.py` | keep `ETHER_NEURO_ES=0` | — |
| 10 | **DSPy MIPROv2 / GEPA prompt optimisation** | proposal calls (4B is a weak proposer) + live evals | 0 | each candidate instruction becomes a bandit arm; promotion via posterior | MIPROv2 up to +13 % (Llama-3-8B); GEPA > MIPROv2 by 10 %, 35× fewer rollouts than GRPO → still hundreds of live attempts per candidate set | med (overfits 60 goals; holdout split required) | new arm texts in `core/learning.STRATEGY_BEHAVIOUR`, max 2 candidates live | `ETHER_PROMPT_OPT=1` | holdout kept/attempt |
| 11 | **OpenEvolve / AlphaEvolve on ETHER's own heuristics with offline evaluators** (SBFL rank formula, goal priority, span window) | 0 on the host; 4B as mutation operator at night, or the owner's tutor | CPU evaluators: `sbfl_bench5` (planted bugs), `bandit_sim` regret | evaluator is an offline benchmark, the change lands via owner review → no live reward to hack | AlphaEvolve found improved algorithms with an evaluator in the loop; for ETHER: SBFL top-1 81.8 % → higher; more goals point at the right function | low (offline), but benchmark overfit → hold out planted bugs | `core/agent/fault_loc.py` scoring, `goal_source.ranked` | `ETHER_EVOLVE_HEUR` (offline script) | SBFL top-1 on held-out bugs |
| 12 | **DGM / HGM / SICA / STOP gated self-modification of the agent's code** | one candidate eval = ~50 goals × 1 attempt ≈ 1 GPU-h; DGM-scale (80 iterations) ≈ 80+ GPU-h per run | git worktree per candidate | must stay **data-level** (prompt addons, arm sets, retrieval k/caps, codemod rules) in an archive, never `core/agent/*.py` | DGM 20→50 % SWE-bench; SICA 17→53 %; HGM human-level with GPT-5-mini — all with frontier models editing themselves; a 4B editing its own scaffold is far weaker → **unproven at 4B** | **high**: DGM faked unit-test logs to look like passes (Sakana write-up); mitigation: the model never reports results, the gate runs pytest itself, protected paths, holdout goals | archive under `memory/learning/archive/`, candidates = config diffs, eval on a frozen holdout goal set | `ETHER_SELF_MOD=archive` | holdout kept/attempt, promotions, revert rate |
| 13 | **Agentless localisation → repair → validation** | — | — | — | Agentless 32 % SWE-bench Lite at $0.70 | — | already the shape of ETHER (SBFL+error text → one function → test gate) | — | — |
| 14 | **LoRA self-training on kept trajectories** (STaR / rejection fine-tuning, SWE-Gym) | n/a online | **infeasible on the host**: inference already uses 2.7 of 4 GB; QLoRA on a 4B needs ~2.4 GB 4-bit weights + 1.5–4 GB activations at 2–4K tokens ⇒ 4–6.5 GB, and Ollama must be stopped (loop halts). TU117 has no tensor cores (~6 TFLOPS FP16 peak): at ~4·N FLOPs/token and ~1.5 TFLOPS effective ≈ 90 tokens/s ⇒ 1,000 trajectories × 1.5K tokens ≈ **4.6 h per epoch if it fit**. CPU: 12 GB RAM < 8 GB bf16 weights + activations + OS ⇒ swap-bound, ~10–30 tokens/s ⇒ 14–40 h/epoch | positives must be gate keeps only | SWE-Gym up to +19 pts from training on its trajectories (2,438 task instances); STaR needs thousands of rationales. ETHER has ≤60 goals ⇒ ≤60 positives today | med (trains on what the gate accepted; weak tests get amplified) | `core/lora_prep.py` → off-box training (≥12–16 GB GPU) → GGUF → Ollama, A/B by time blocks | `ETHER_LORA_TRAIN` (stays 0) | only after ≥500 kept trajectories (needs #3) |

## 5. Roadmap after the batch 2–6 push

All A/Bs use the bandit itself: a new option is an **arm** (or a flag-blocked time window when it changes the
model call itself), compared against `default` on the attempts where both were eligible, accepted with the
existing posterior rule. Acceptance needs **all** of: P(option beats default) ≥ 0.9; revert rate not higher by
> 0.05; regressions caught per kept edit not higher; filler rate = 0; spoiler share not higher.

**Sample sizes** (per arm, power 0.8; "P ≥ 0.9" ≈ one-sided α = 0.10, which is what `PROMOTE_PROB` means):

| baseline → option kept/attempt | one-sided α 0.10 (P ≥ 0.9) | two-sided α 0.05 | hours at 60 attempts/h, 2 arms |
|---|---:|---:|---:|
| 0.05 → 0.15 | 79 | 138 | 2.6 (4.6) |
| 0.10 → 0.25 | 56 | 97 | 1.9 (3.2) |
| 0.10 → 0.20 | 113 | 197 | 3.8 (6.6) |
| 0.20 → 0.30 | 167 | 291 | 5.6 (9.7) |
| 0.10 → 0.15 | 393 | 683 | 13 (23) |

So with ~360 slots in today's pool, ETHER can resolve **one** +10-point effect per pool, and cannot see +5-point
effects at all. That is why bug-injection goals (#3) move up to Phase 1.

### Phase 0 — measure the baseline (first 1–6 h after the push; no flags)
- Run `python scripts/first_hour_report.py --fetch` at 1 h and 6 h. Record: kept/attempt, kept per GPU-hour (`secs`), revert rate, regressions caught, filler rate (must be 0), arm spread (top share ≤ 0.6), commits/h (≤ 12), median `secs` per attempt, hours to pool exhaustion.
- New Phase-0 number to add: **duplicate-reply rate** (same `reply_tail` for the same goal on a later try) — decides whether #2 is worth it.
- Set `ETHER_EXEMPLARS=record` during Phase 0: it only stores gate-kept diffs (private `memory/learning/exemplars.json`), prompts stay byte-identical, so the library is warm when Phase 1 starts.
- Exit: ≥ 100 graded real attempts, or the pool is empty.

### Phase 1 — cheap, high-ROI (week 1)
1. **`ETHER_EXEMPLARS=1`** (prototype ready, §6). A/B as the 6th arm; only offered when a non-leaking exemplar exists. Accept per the rule above; expected n ≈ 56–113 per arm.
2. **`ETHER_SAMPLE_TEMP` + `ETHER_DEDUP_REPLY`** if Phase 0 duplicate rate ≥ 30 %. It changes decoding for all arms, so A/B by alternating 2-hour blocks (flag on/off), metric pass@k by try index and kept per GPU-hour.
3. **`ETHER_MUTANT_GOALS=1`** (pool replenishment): deterministic AST mutants only on functions whose tests kill them; scratch apply; separate kind/table/metrics. Accept when the open pool never hits 0 for 24 h and real-goal kept/attempt doesn't drop.
4. Fix the `Pipeline.__init__` spoiler false positive.

### Phase 2 — skill library + diversity (weeks 2–3, needs #3 for sample size)
5. **Skill library** (`ETHER_SKILL_LIB`): exemplars that keep ≥ 3 times on different goals graduate; rule-based codemods (`refactor.py`) are the first tool skills; fabricate→quarantine→promote re-gated by the honest gate. Metric: skill reuse rate ≥ 20 % of keeps, % of keeps that use 0 GPU-s.
6. **MAP-Elites over prompt programs** (`ETHER_QD`), replacing the 5 hand-made arms with a grid of context × retry × exemplar × style. Accept if the best cell beats the incumbent by the posterior rule on held-out goals.
7. **Hierarchical prior** (`ETHER_BANDIT_HIER`) once ≥ 3 goal kinds have ≥ 50 attempts each.

### Phase 3 — gated self-modification (month 2+)
8. **DGM-style archive of data-level policies** (`ETHER_SELF_MOD=archive`): a candidate is a config diff (arm texts, retrieval caps, temperatures, codemod rules), proposed by the 4B at idle or by the owner's tutor; evaluated on a frozen 30 % holdout goal set; archived with its score; promoted by the posterior rule; code changes to `core/agent/` stay owner-reviewed. Accept if holdout kept/attempt ≥ incumbent + 0.05 with P ≥ 0.9 and revert rate not higher.
9. **OpenEvolve on heuristics** with offline evaluators (SBFL top-1 on held-out planted bugs; bandit regret in `bandit_sim`). Owner reviews every landed change.
10. **Prompt optimisation** (GEPA/MIPRO-style) through the same archive.
11. **LoRA**: off-box only, after ≥ 500 kept trajectories (needs #3), adapter evaluated as a time-blocked "model arm".

### Metrics (all from `trajectories.jsonl` / `learning_summary.json`)
kept/attempt · kept per GPU-hour · revert rate · regressions caught · filler rate (= 0) · arm spread (entropy, top share) · time-to-first-keep per goal · hours to pool exhaustion · duplicate-reply rate · exemplar shown / kept-when-shown / reuse rate (b7) · skill reuse rate (Phase 2) · holdout kept/attempt (Phase 3).

## 6. Prototype: kept-edit exemplars (`ETHER_EXEMPLARS`, default 0 = off) — **b7**

- `core/agent/exemplars.py` (new). On the honest gate's **keep** branch only (`sota.py` keep path), stores the target function's before/after unified diff (≤ 520 chars), the error kind/text and tokens, in `memory/learning/exemplars.json` through `core.spine.state_io.rmw` (single-writer rule D3; checked with the D3 scanner: 0 new writer sites). Never published.
- Retrieval: idf-weighted token overlap on error text + test name + symbol, +0.1 for the same error kind; min score 0.08; top-1.
- Anti-leak: never the same goal id, test node id, or (file, symbol); never a diff that defines or assigns the goal's own short name (that would also trip the spoiler guard and burn the goal). The spoiler guard still runs on the full prompt.
- Bandit: with `=1`, `exemplar` is a 6th arm, offered **only** when a non-leaking candidate exists (no wasted cold-start pulls); `exemplar_eligible` is logged on every real attempt so the A/B compares like with like. Reward is unchanged: the gate's 0/1 for the new goal.
- `=record` stores kept diffs only; prompts are byte-identical (tested).
- Visibility: trajectory field `exemplar` (the id shown), `learning_summary.json["exemplars"]` (library, shown, kept-when-shown, kept/attempt shown vs other, reuse rate; counts only, no diffs), and a line in `first_hour_report.py`.

**Measured (no model; `docs/results/batch7/exemplar_replay.py` → `exemplar_replay.json`), real goal seed, 60 goals:**

| | 4K ctx | 8K ctx |
|---|---:|---:|
| goals with a non-leaking exemplar (leave-one-out, library = other 59) | 60/60 | 60/60 |
| candidates excluded by the leak rules | 140 | 140 |
| spoiler trips added by the exemplar block | **0** | **0** |
| spoiler trips already in the base prompt (`Pipeline.__init__` ×2) | 2 | 2 |
| prompts over the context budget | 0 | 0 |
| hint actually shown (room left after reserving the code context) | 60/60 | 60/60 |
| code context (function / span window) cut by the hint | 0 | 0 |
| block chars median / max | 400 / 515 | 400 / 515 |
| same-file exemplar share | 0.10 | 0.10 |

Growth curve (random order, each goal kept with p = 0.2, 10 seeds): coverage of the next goal is 0.89 with a
library of 1, 0.74–0.95 with 2–9, 0.86–1.0 with 10–14. This uses stand-in diffs, so it measures plumbing,
coverage and safety, **not** the gain; the gain is the Phase 1 A/B.

**Mock replay** (`tests/test_batch7_exemplars.py`, 12 tests): a pattern-copying fake model fixes `clamp_low`
alone and `floor_at` only when shown the `max()` diff. Flag off/record: `floor_at` is never kept (6 tries).
Flag 1: `clamp_low` kept first (exemplar arm not offered, library empty, `exemplar_eligible=false`), then
`floor_at` kept under the `exemplar` arm with 0 regressions, `reward01=1`, trajectory `exemplar=<clamp goal id>`.
A wrong reply after an exemplar is still reverted. Leak rules, min-score cut-off, budget fit at 2K/4K/8K, the
spoiler guard, the span window staying whole at 2K/4K, and the `first_hour_report` line are each tested.

**Full suite** (`pytest tests -q -p no:cacheprovider`): before 1,935 tests, 1,778 pass / 74 fail / 83 skip;
after 1,947 tests (12 new), 1,790 pass / 74 fail / 83 skip; **0 new failures**, 0 fixed, 0 removed; no dirty
paths (`docs/results/batch7/tests_summary.json`).

## 7. Sources (each returned HTTP 200 on 2026-11-21)

Bandits / OPE: Thompson sampling tutorial https://arxiv.org/abs/1707.02038 · LinUCB https://arxiv.org/abs/1003.0146
Memory / experience: Reflexion https://arxiv.org/abs/2303.11366 (code https://github.com/noahshinn/reflexion) · ExpeL https://arxiv.org/abs/2308.10144 · Voyager https://arxiv.org/abs/2305.16291 · Agent Workflow Memory https://arxiv.org/abs/2409.07429 (code https://github.com/zorazrw/agent-workflow-memory)
Self-modifying agents: Darwin Gödel Machine https://arxiv.org/abs/2505.22954 (code https://github.com/jennyzzt/dgm; reward-hacking note https://sakana.ai/dgm/) · Huxley-Gödel Machine https://arxiv.org/abs/2510.21614 · SICA https://arxiv.org/abs/2504.15228 (code https://github.com/MaximeRobeyns/self_improving_coding_agent) · STOP https://arxiv.org/abs/2310.02304 · Reward hacking in practice (METR) https://metr.org/blog/2025-06-05-recent-reward-hacking/
Evolutionary: AlphaEvolve https://arxiv.org/abs/2506.13131 and https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/ · OpenEvolve https://github.com/codelion/openevolve · MAP-Elites https://arxiv.org/abs/1504.04909 · pyribs https://github.com/icaros-usc/pyribs · EvoPrompt https://arxiv.org/abs/2309.08532 · Promptbreeder https://arxiv.org/abs/2309.16797
Test-time scaling / SWE pipelines: Large Language Monkeys https://arxiv.org/abs/2407.21787 · Scaling test-time compute https://arxiv.org/abs/2408.03314 · CodeT https://arxiv.org/abs/2207.10397 · Agentless https://arxiv.org/abs/2407.01489 (code https://github.com/OpenAutoCoder/Agentless) · AutoCodeRover https://arxiv.org/abs/2404.05427
Prompt optimisation: DSPy https://arxiv.org/abs/2310.03714 (https://github.com/stanfordnlp/dspy) · MIPROv2 https://arxiv.org/abs/2406.11695 · GEPA https://arxiv.org/abs/2507.19457
Self-generated tasks / training: SWE-smith https://arxiv.org/abs/2504.21798 · Self-play SWE-RL https://arxiv.org/abs/2512.18552 · SWE-Gym https://arxiv.org/abs/2412.21139 · STaR https://arxiv.org/abs/2203.14465 · SWE-RL https://arxiv.org/abs/2502.18449 · QLoRA https://arxiv.org/abs/2305.14314 · Unsloth https://github.com/unslothai/unsloth
