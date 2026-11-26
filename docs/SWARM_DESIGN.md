# Practical swarm-agent designs for ETHER (2026-11-26, branch ether-swarm-docs)

Base: `ether-batch10` @ `20d0f617f2` (this docs branch is rooted there). Later batch-10 commits
through `5f2c3ed997` were **read** from the sibling worktree (items 1, 4, 5, 6, 7) and are not
merged here. Research and design only. **No live path is changed on this branch.** Nothing is
pushed. `/workspace/ether-b10` was not edited. Companion to `docs/MULTI_AGENT_RL.md` (branch `ether-marl-docs`: extra 4B
roles raised kept/attempt 0.107→0.131 and cut kept/GPU-hour 10.1→6.5 under *stated* priors with
an 8 s guard) and `docs/RL_METHODS.md`.

Doctrine held throughout: single writer (`scripts/host_main.py`), Matrix read-only, tool-first,
honest gate only (a tool edit + the target test passing + 0 regressions; generate-only is never a
PASS), GTX 1650 4 GB + `qwen3.5:4b` via ollama, `ETHER_NUM_CTX=4096`, **one model call at a time**,
no second installer, no weight training, no MAPPO/GRPO, no GPU fan-out. Reward is the gate's 0/1
(`core/agent/outcome.py` `reward01`). Pregates, critics, and judges may only **veto or rank**.

All "sim" numbers below are a **SIMULATION** with live-calibrated rates and stated assumptions,
not a 1650 measurement of a swarm (no swarm has run). Script: `scripts/swarm_sim.py`. Results:
`docs/results/swarm/swarm_sim.json` (200 seeds). The live calibration *is* a 1650 measurement:
`artifacts/learning_summary.json` generated 2026-11-26T17:47:48Z, `real_graded=238`,
`real_passes=2`.

----------------------------------------------------------------------------------------------------

## Verdict

A swarm that fits the 1650 is **not** a second 4B, a debate, or a GPU fan-out. It is a bag of
**deterministic gem agents** around one proposer, plus **scouts that keep the goal queue
selectable**, with optional **serial best-of-N** once the queue is flowing.

The live host has already disproved the planning costs in the MARL study. The guard is not 8 s:
a completed attempt is ~245 s (baseline pytest ~160 s *before* the model, one 4B call ~30 s,
after-edit guard ~55 s; live regression rows 245–272 s). The 8 s figure made a second 4B call
look expensive; on the real cost bill a second call is ~+13% and a skipped after-gate is ~55 s.
The baseline pytest, however, **cannot** be skipped by a critic of the edit — `sota._attempt_real`
runs it first, and the honest gate needs it. So the only pytest you can save is the after-run,
and the only way to raise kept/attempt without extra GPU is better goals, better context, or
more than one sample after that already-paid baseline.

Live rates also change the story: **2 keeps in 238 real attempts (0.0084)**, 0/133 on SBFL, 2/87
on `test_import`, `dup_share=0.1846`, 22 regressions reverted, and a 44-hour idle (health still
says "goal queue empty" while 95 goals sit open — batch 10 item 0 fixes the accounting and the
timeout that exhausted every try). `filler_rate=0.9556` is **not** a real-goal filler rate: it is
the share of *all* kept rows, including 43 legacy filler keeps. The two real keeps are not filler.

**Ship, flag-gated, in this order:**

1. **Phase A, no extra 4B calls** (options 1+6): item 0 is already on the batch-10 branch;
   turn on the already-built single-call pregates and dry-refill (`ETHER_LSP_PREGATE`,
   `ETHER_GEM_PREGATE`, `ETHER_DEDUP_REPLY`, `ETHER_PLANTED_GOALS` when `selectable=0`,
   `ETHER_GOAL_LIVE_ONLY`, `ETHER_SAMPLE_TEMP=0,0.7`) and add scouts that interleave
   `test_import` with SBFL. Leave `ETHER_SWARM` at 0. Can only reject or add context.
2. **Phase B, `ETHER_SWARM=1` with `ETHER_SWARM_K=2`** (option 4, after the queue is flowing):
   item 5 already built this (default K is 3 — start at 2). Serialized 4B samples, CPU screens,
   at most one after-gate. Kill it if kept/GPU-hour falls. Raise K only after a success.

**Do not ship:** a 4B critic (false-reject of a rare keep), debate, mixture-of-agents, or a
population of prompt arms. Do not implement `ETHER_SWARM_LIVE` (GPU fan-out). Leave
`core/loop/coord.py` (`spawned=False`, `MAX_LIVE_AGENTS=1`) as the lock it already is.

These are simulations. The 15% SBFL-localizer lift and the planted keep rate (0.08) are
assumptions; `loc_off` and `sparse` show when the gains shrink. Measure on the 1650 with
`scripts/first_hour_report.py`.

----------------------------------------------------------------------------------------------------

## Ranked table (sim, homogeneous MLE, iid T=238, 200 seeds)

Cost and rates below are for an **infinite mix** at the live via shares — what you would see if
scouts keep finding new real goals at today's mixture. The 48-hour *finite-pool* column is the
more honest host picture (95 open goals × 3 tries, then idle unless refill is on). Baseline
recovers the live keep rate (sim 0.0085 vs live 0.0084) and nearly the live GPU-hour figure
(0.130 vs 0.134; the gap is the post-batch-10 completed-attempt cost of 234 s vs the live 225 s
blend, which still includes ~185 s timeout aborts).

| Option | Fit | GPU cost / att. | Sim kept/att | kept/GPU-h | After-gates saved | 48h pool: real keeps / idle | Verdict |
|---|---|---|---|---|---|---|---|
| Baseline (post-b10, flags off) | reference | 1 × 4B + 234 s | 0.0085 | 0.130 | 0 | 2.38 / **29.6 h dry** | Reference. Still starves once the 95-goal pool is exhausted. |
| **1+6 gems + goal-flow** | **best overall** | 1 × 4B, cheaper after-gate | **0.0176** | **0.282** | 0.22 | 2.90 real + 22.5 planted / **0 h** | **Ship first, without multiplying model calls.** Item 5 already used `ETHER_SWARM=1` for BoN; leave that off until Phase B. |
| 6. Goal-flow scouts only | best for the outage | 1 × 4B | 0.0160 | 0.245 | 0 | 2.47 + 22.1 planted / 0 h | Ship with #1. Ends the empty-queue outage. |
| 1. Zero-model gem swarm | best fit, no refill | 1 × 4B, cheaper after-gate | 0.0100 | 0.161 | 0.22 | 2.81 / 30.5 h dry | Ship, but without scouts it still dries. |
| **1+6+4 gems + flow + BoN=2** | **best follow-on** | 2 × 4B serial | **0.0323** | **0.444** | 0.26 | **5.51** real + 33.9 planted / 0 h | **Phase B: `ETHER_SWARM=1` with `ETHER_SWARM_K=2`** (item 5 already built this; default K is 3 — start at 2). |
| 4. Best-of-2 + prefilters | good once flowing | 2 × 4B serial | 0.0168 | 0.231 | 0.26 | 4.46 / 27.6 h dry | Same flag; still dries without scouts. |
| 4. Best-of-4 + prefilters | heavier | 4 × 4B serial | 0.0311 | 0.341 | 0.27 | 8.04 / 22.8 h dry | Hold until BoN=2 is measured. |
| 2. Hierarchical bag | poor at this n (see note) | 1 × 4B | 0.0131 | 0.202 | 0 | **2.29 / 29.6 h** | The iid lift is "prefer test_import", a scout rule. In a finite pool it can exhaust the only solvable slice first. Do not add prompt arms. |
| 3b. Deterministic critic | good, subset of #1 | 1 × 4B | 0.0079 | 0.127 | 0.22 | 2.46 / 30.4 h | Ship as part of #1, not a separate role. Slightly below baseline when there is no localizer (`loc_off`: 0.0086 vs 0.0079, noise / 1% false-reject). |
| 3a. 4B critic (veto only) | weak | 2 × 4B | 0.0074 | 0.106 | 0.24 | 2.37 / 28.3 h | Do not ship. A 4B false-reject of a rare keep is too expensive. |
| 5. Planted curriculum | good when dry | 1 × 4B + validation | 0.0259 (real 0.0075) | 0.399 (real 0.087) | 0 | 2.27 + 21.3 planted / 0 h | Turn on **when `selectable=0` only** (`ETHER_PLANTED_GOALS`, already built). A 25% mix while real goals remain *lowers* real kept/GPU-hour. |
| 7a. Debate + 4B judge | reject | 3 × 4B | 0.0086 | 0.109 | 0.24 | 2.29 / 25.9 h | No coverage gain, judge can kill a keep. |
| 7b. Mixture-of-agents | reject | 5 × 4B | 0.0283 | 0.285 | 0.27 | 7.33 / 20.5 h | Strictly worse best-of-4 on GPU-hour (0.285 vs 0.341). |
| 7c. Prompt-evolution | reject | 1 × 4B | 0.0078 | 0.120 | 0 | 2.37 / 29.6 h | Dilutes 2 keeps across more arms. `ETHER_NEURO_ES` already exists and must not self-promote. |

Filler in this sim is 0.0 for every real/planted option: the live 0.9556 number is legacy keeps and
must not be used as a real-goal KPI (`outcome.metrics` should be split; see § telemetry).

----------------------------------------------------------------------------------------------------

## 1. Inventory (what is actually there, batches 2–10)

This updates `docs/MULTI_AGENT_RL.md` §1 against `ether-batch10` and the live host.

- **Eight gem packages** still exist (`gems/protocol.py`). Only Clear Quartz is a live sandbox on
  a legacy path. The real-goal loop still does not call those packages. The "bag of decisions" is
  still five hard-coded rules in `core/agent/gems.py:99` `chain()` (security / route / profile /
  fabricate / memory-evolve). `route_stage` uses `by_id` for metadata only.
- **One new real-path hook:** `ETHER_GEM_PREGATE` (batch 9, default off) puts Black Tourmaline
  between `apply_edit` and the gate (`core/agent/pillars.py`, called from `sota._attempt_real`).
  It can only reject. That is the pattern every new "agent" must copy.
- **The writer** is still `host_main._tick` → `_learn` → `sota._attempt_real`. Order on a
  selectable goal: baseline pytest → build prompt (bandit arm, optional exemplar) → one 4B
  ReAct call (`turns=2`) → extract edit → optional dedup skip (`ETHER_DEDUP_REPLY`) → apply →
  optional security pregate → `goal_source.gate` (after-edit pytest) → keep or restore. Only
  `host_main` applies edits, only through that gate.
- **Bandit:** Thompson over `REAL_ARMS`, reward 0/1, no promotions (2 real keeps, posteriors
  still prior-like). `ETHER_BANDIT_FACTORED` / `_COST` / `_HIER` are off.
- **Planted goals, live-only filter, temperature ladder, dedup** are already built and off
  (`ETHER_PLANTED_GOALS`, `ETHER_GOAL_LIVE_ONLY`, `ETHER_SAMPLE_TEMP`, `ETHER_DEDUP_REPLY`).
  Live `dup_share=0.1846` is already above the 15% rule for turning `ETHER_SAMPLE_TEMP=0,0.7` on.
- **learn.py ladder** is the legacy curriculum on `context_budget.py`. The real-goal path does
  not use it. A swarm must not route through `Pipeline` or that ladder.
- **Batch 10 in `/workspace/ether-b10` (read 2026-11-26, do not edit).** By the time this
  study was finished, `ether-batch10` had moved to `5f2c3ed997` (ahead of this branch's base).
  All items 0–7 are committed there:
  - Item 0: idle-queue root cause + adaptive timeout + re-admit.
  - Item 1: 44 unreachable files `git mv`'d to `attic/` (reversible, not deleted).
  - Item 2: `ETHER_GATE_JAIL`. Item 3: real MCP client + read-only status server.
  - Item 4 (`17ac6af014`): `core/agent/lsp_client.py`. `ETHER_LSP=1` (read-only `lsp` tool) and
    `ETHER_LSP_PREGATE=1` (added error-severity diagnostics reject the edit and skip the
    after-gate). That pregate *is* a piece of option 1. Both default off.
  - **Item 5 (`90b0a3a37d`): a proposer swarm, already landed, default off.** See §5.
    `core/agent/swarm.py` + hook in `sota._attempt_real`: `ETHER_SWARM=1` runs K serialized
    4B proposals (default `ETHER_SWARM_K=3`, max 4; candidate 0 at the normal temperature,
    others at `ETHER_SWARM_TEMP=0.7`), CPU workers screen each reply in memory (extract,
    compile, security-gem pre-check, drop reverted and intra-batch duplicates), and the
    writer applies only the best survivor through the unchanged honest gate (one after-gate
    per try). `model_lock()` keeps generations serial. If the client cannot take a
    temperature, K is forced to 1.
  - Item 6–7: `docs/AUDIT_TODO.md`, `docs/BATCH10.md`, FLAGS rows. `PRODUCT.md` is still
    unchanged ("Not this product: … a swarm"); `STATUS.md` leaves turning the swarm on, and
    whether PRODUCT.md needs a wording change, as an owner decision. `core/loop/coord.py`
    still forbids spawn and GPU fan-out. `ETHER_SWARM_LIVE` (GPU fan-out) was moved to
    `attic/` with the phase-5 flags and must stay off.

----------------------------------------------------------------------------------------------------

## 2. Cost model (the number that changed)

```
sota._attempt_real:
  run_pytest(suite)          T_BASE  ≈ 160 s   # always, before the model
  4B proposer                T_MODEL ≈  30 s   # planning number, same as bandit_sim / marl_sim
  gate() = run_pytest again  T_AFTER ≈  55 s   # only if an edit was applied
  CPU AST/LSP/lint           T_PRE   ≈   2 s
```

Fit: 160+30+55 = 245 s matches live `note=regression` rows (245.6, 246.2, 247.8, 272.8 s).
160+30 = 190 s is in the `no_function` range (180.7, 230.4 s). Live mean 225.45 s/attempt
(`gpu_hours=14.903` / 238) still includes baseline-timeout aborts at ~185 s with no model
(18 of the last 25 rows). Batch 10 item 0 classifies those as `no_attempt`, so the post-batch-10
baseline used in the sim is the completed-attempt expectation **234 s**
(`T_BASE+T_MODEL+(1-0.20)*T_AFTER`, 20% no-edit is a stated assumption — the full 238-row note
breakdown was not in `learning_summary.recent`).

Consequences, opposite to the MARL study's 8 s guard:

- A second serial 4B call is cheap relative to the already-paid baseline (**this is when BoN
  wins**).
- A 4B critic that only vetoes must skip more than `T_MODEL/T_AFTER ≈ 55%` of after-gates *and*
  almost never kill a keep, or it loses. The sim's 30% veto / 8% false-reject 4B critic loses
  (0.0074 / 0.106 vs 0.0085 / 0.130).
- When the after-gate is cheap again (`cheap_after`, 8 s), pregate savings shrink and extra
  model calls look worse on GPU-hour, recovering the MARL qualitative result.

----------------------------------------------------------------------------------------------------

## 3. The seven options (integration, telemetry, failure modes)

Every option plugs into `_attempt_real` / `goal_source.next_real` inside the `host_main` process.
No second writer, no gem HTTP server, no Matrix write, no `Pipeline.run` on the host tick.
Intermediate output is prompt text or a rejected candidate, never a committed patch. Revert
stays `sota.revert` + `TreeGuard`.

### 1. Zero-model-call swarm (gems as deterministic agents)

Agents, all CPU, around one 4B proposer:

| Agent | Gem / module | What it may do | What it may not do |
|---|---|---|---|
| Localizer | SBFL already on; LSP diagnostics / import graph (item 4) | Add span / symbol / diagnostic context to the prompt | Call the 4B, shrink the honest guard |
| Security pregate | Black Tourmaline, `ETHER_GEM_PREGATE` (built) | Veto an edit that *adds* a dangerous call | Keep an edit |
| AST / lint critic | Labradorite shape + parse / ruff | Veto unparseable or newly-introduced lint errors | Keep an edit |
| LSP pregate | item 4 `ETHER_LSP_PREGATE` | Veto added error-severity diagnostics | Keep an edit |
| Test-selector | existing `guard_suite` / siblings | Choose *prompt* tests (which failures to show) | Shrink the after-gate suite |
| Dedup filter | `ETHER_DEDUP_REPLY` (built, off) | Skip the after-gate on a byte-identical reverted edit | Invent a PASS |

**Bandit / planted / ladder:** no new arms. Pregate rejects are reward 0, same as any missed
reply (this *does* change what the bandit sees; that is why the flag stays off until a
`record` shadow pass shows no would-reject on a keep). Planted goals, when on, run through the
same bag in the scratch copy. `learn.py` is untouched.

**Telemetry:** `swarm_mode`, `pregate_rejects` (by agent), `dedup_skipped`, `after_gate_skipped`,
`secs_saved`, `lsp_errors_added`, `loc_symbols`.

**Failure modes:** (a) false-reject of a would-keep — catastrophic at 2/238, hence shadow mode
first; (b) localizer lift is the main assumed gain (15% of SBFL mass inherits the 2/87 rate).
Under `loc_off` this option is ~tied with baseline on kept/attempt (0.0079 = 0.0079) and only
slightly better on GPU-hour (0.127 vs 0.121) from skipped after-gates; under `loc_strong` (40%)
it jumps to 0.0140 / 0.225. (c) Without scouts the finite pool still dries (~30 h idle in 48 h).

### 2. Hierarchical bag-of-decisions

Top Thompson picks a via-policy (live mix vs prefer-`test_import`); lower Thompson would pick a
prompt arm. Gems could also expose discrete decisions (context on/off, temperature, which tests
to show) as arms.

**The iid lift (0.0131 / 0.202) is not evidence for more prompt arms.** It is the top policy
learning "prefer test_import" — which a scout can hard-code today, and which the 0/133 vs 2/87
split already justifies without a bandit. In the 48-hour *finite* pool that same greedy preference
**exhausts the only solvable slice first** (2.29 real keeps, ≤ baseline 2.38) and then grinds
SBFL at p≈0. Two real keeps also cannot identify a 5-arm or 5×N joint (`MULTI_AGENT_RL.md`:
even at p≈0.10 a 20-cell joint was not locked after 1000 attempts).

**Failure modes:** arm dilution, finite-pool starvation of the good via, treating a scout rule
as a learned role. **Do not add arms.** Put prefer-import *interleaved* (not "until empty") in
option 6.

### 3. Proposer → critic → solver, critic veto only

One 4B proposer, then either a short 4B critic call or a deterministic critic, then the gate
(no second "solver" call unless you are actually doing BoN). The critic may only veto.

**4B critic:** 0.0074 / 0.106, worse than baseline. False-reject 8% of rare keeps is enough to
lose, and a 4B is a weak test predictor (the tests already are the critic). Under
`expensive_model` (90 s/call) it falls to 0.080 kept/GPU-hour vs baseline 0.105.

**Deterministic critic:** overlaps option 1 without the localizer. Ship it there.

### 4. Best-of-N + deterministic prefilters

One baseline, N *serial* 4B samples (diverse: `ETHER_SAMPLE_TEMP` or T>0 on retries), prefilters
pick at most one candidate for the after-gate. Coverage ≈ `1-(1-p)^{unique}` if attempts are
homogeneous (Chen et al. Codex pass@k; Brown et al., Large Language Monkeys). Live `dup_share`
0.1846 at T=0 would collapse uniqueness; the sim uses a 0.08 duplicate rate when diverse.

- Homogeneous iid: BoN=2 → 0.0168 / 0.231; BoN=4 → 0.0311 / 0.341.
- **Sparse** (mean p matches the MLE, but only a small easy subset is solvable at p=0.30 — the
  pessimistic reading of 2/238): BoN=2 shrinks to 0.0130 / 0.179; BoN=4 to 0.0199 / 0.219.
  In the 48-hour sparse *pool*, BoN=4 only reaches 2.60 real keeps vs baseline 1.78, because
  unsolvable goals stay unsolvable. **BoN cannot invent coverage that is not there.**
- `high_dup` (0.40, T=0, no diversity): BoN still helps in the sim but less than with
  `DUP_TEMP=0.08`; turn `ETHER_SAMPLE_TEMP=0,0.7` on first (already indicated by live 18.5%).
- `expensive_model`: BoN=2 still beats baseline (0.152 vs 0.105) but the margin shrinks; BoN=4
  should wait.

**Failure modes:** N samples wasted on a via with p=0 (SBFL today); aggregator-free is fine
(prefilters, not a 4B judge); budget N to remaining wall-clock.

### 5. Planted-bug proposer/solver curriculum (self-play)

Already built (`core/agent/planted.py`). A proposer (mutation operators, no 4B required) plants
a validated single-site bug in a scratch copy; the solver is the ordinary real-goal attempt;
proposer credit is the later kept solve, never a raw fail count; never published.

Sim assumption `P_PLANTED=0.08` (easier than live real 0.0084 — single-site, validated). A 25%
mix *while the real pool is still open* raises total kept/attempt to 0.0259 but **drops real**
kept/GPU-hour to 0.087 (iid) / 0.047 (48 h pool). When used only as a refill after
`selectable=0`, planted time has no opportunity cost in real keeps (the alternative is idle).
That is the flag as already specified.

**Failure modes:** distribution shift (the 4B learns to undo comparison flips, not fix SBFL
bugs); publishing a mutant (forbidden); counting planted keeps as product progress (split the
KPI). Transfer to real goals is not modelled as a keep-rate bonus; it would show up later, if at
all, in arm posteriors and exemplars recorded from scratch solves — and those exemplars must
stay scratch-tagged so they are not injected into real prompts as if they were product edits.

### 6. Goal-flow swarm (scouts, no model calls)

Scouts refill and rank the queue from failing tests, SBFL clusters, lint, and planted (when
dry). This is the option that addresses the actual outage: 95 open goals, 0 selectable, 44 h
idle, health "empty".

Batch 10 item 0 already re-admits exhausted goals, parks baseline aborts without spending a try,
and stops calling a non-empty queue "empty". Scouts on top should: (a) prefer `test_import` but
**interleave** SBFL (do not drain the only via that has kept and then stall — see option 2's
finite-pool failure); (b) skip targets the writer never imports when `ETHER_GOAL_LIVE_ONLY=1`;
(c) call `planted.generate` only when `selectable=0`; (d) refresh the failing-test scan when
dry (`ETHER_GOAL_SCAN` already exists).

Iid (infinite new real goals at the reweighted mix): 0.0160 / 0.245, no extra model call.
48-hour pool: idle 0, real keeps ≈ baseline (2.47 vs 2.38) plus ~22 planted curriculum keeps.

**Failure modes:** ranking by a noisy Laplace prior that would put lint (0/12) above
`test_import` (the sim caps that); starving SBFL forever; treating planted keeps as real.

### 7. Population / debate / mixture-of-agents (reject, quantified)

- **Debate** (proposer + critic + judge = 3 serial 4B calls): 0.0086 / 0.109, worse GPU-hour than
  baseline, no pass@N coverage gain (one proposal, a judge that can only veto). Even under
  optimistic literature claims for *reasoning* tasks (Du et al. 2023), the 1650 pays 3× model
  time and still needs the after-gate.
- **MoA** (4 proposers + aggregator = 5 calls): 0.0283 / 0.285 vs BoN=4 0.0311 / 0.341. The
  aggregator (modelled as 0.9× pass@unique) can drop a good candidate and always pays an extra
  call. Together Computer 2024 is not a 4B-on-4GB result.
- **Prompt-evolution / PBT / CMA-ES:** 0.0078 / 0.120, statistically baseline. Two keeps cannot
  train a population. `ETHER_NEURO_ES` already exists and is forbidden to self-promote.

----------------------------------------------------------------------------------------------------

## 4. Sensitivity — when each option wins or loses

| Condition | Who wins | Who loses |
|---|---|---|
| Live-like homogeneous iid, T_MODEL=30 s, T_AFTER=55 s | gems+flow; BoN=2 on top | 4B critic, debate |
| Sparse solvable subset (p_easy=0.30, mean held to the MLE) | gems+flow still ~2×; BoN=2 shrinks (0.0130 vs 0.0168); BoN=4 shrinks more (0.0199 vs 0.0311) | Anyone counting on pass@N to "unlock" SBFL |
| `loc_off` (localizer lift = 0) | goal-flow (mix only) and BoN; gems swarm ≈ baseline on kept/attempt, small GPU-hour win from skipped after-gates | Option 1's *assumed* SBFL lift |
| `loc_strong` (40% of SBFL becomes test_import-like) | gems swarm 0.0140 / 0.225, ahead of BoN=2 without flow | — |
| Finite 95-goal pool, 48 h wall | BoN raises *real* keeps on the pool (4.46 / 8.04); gems+flow+BoN=2 is best overall (5.51 real, 0 idle). Greedy prefer-import alone does not beat baseline on real keeps. | Policies with no refill (29 h dry); 25% planted mix while real goals remain (real kept/GPU-h drops) |
| `cheap_after` (8 s) | Mix / loc / BoN still raise kept/attempt; pregate savings shrink | Recovers the MARL qualitative result that extra 4B roles are a harder sell |
| `expensive_model` (90 s/call) | gems+flow (no extra call) 0.210 vs baseline 0.105; BoN=2 still ahead (0.152) but less so | 4B critic 0.080; debate; MoA |
| `high_dup` (0.40) at T=0 | Dedup / pregate savings grow; BoN needs `ETHER_SAMPLE_TEMP` | BoN uniqueness |

**Laplace prior** (sensitivity only, lint capped at test_import) does not change the ranking;
it must not be used to promote lint over the only via that has kept.

----------------------------------------------------------------------------------------------------

## 5. Flag-gated spec vs what batch 10 item 5 already built

Item 5 has **landed** on `ether-batch10` @ `90b0a3a37d` (docs in `5f2c3ed997`). It is a
doctrine-compatible **option 4 (best-of-K)** with a **subset of option 1's CPU screens**,
serialized through `model_lock`, default off. That is the right *shape*. It is not the
ranking in § Verdict, and a few defaults and gaps should change before it is turned on.

### What to keep (item 5 got these right)

- One writer, one loaded model, one after-gate per try, candidates screened **in memory**
  (no write until the chosen edit). `core/loop/coord.py` stays the fan-out lock.
- Serialized model calls (`model_lock` + `artifacts/model.lock`, stale lock broken at 30 min).
- CPU screens overlapping the next generation: extract, compile, security-gem pre-check,
  drop reverted-before and intra-batch duplicates. Workers never touch the repo.
- Candidate 0 at the normal temperature schedule, others at 0.7 — and K=1 if the client
  cannot take a temperature.
- Default **off**. FLAGS already say `ETHER_SAMPLE_TEMP=0,0.7` and `ETHER_DEDUP_REPLY=1`
  first, and `ETHER_SWARM=1` only once per-attempt time is known.

### What to change (follow-up on item 5, or flags on the PC)

1. **Do not turn `ETHER_SWARM=1` on as the first swarm flag.** The sim says the first win is
   zero-extra-call: scouts + planted-when-dry + LSP/security/AST pregate + dedup around
   *one* proposer (`ETHER_SWARM` left at 0). Item 5 as built *always* spends K model calls
   when enabled; there is no `record` / `gems` mode that adds context and pregates without
   multiplying GPU time. Add that, or just turn the already-built single-call pregates on
   first: `ETHER_LSP_PREGATE=1`, `ETHER_GEM_PREGATE=1`, `ETHER_DEDUP_REPLY=1`,
   `ETHER_PLANTED_GOALS=1` when `selectable=0`, `ETHER_GOAL_LIVE_ONLY=1`.
2. **Start at K=2, not K=3.** Default `ETHER_SWARM_K=3` is +60 s of model time per try
   (between the simulated BoN=2 and BoN=4). Phase B success/kill in this study is written
   for BoN=2 (1.5× kept/attempt, GPU-hour not down >10%). Set `ETHER_SWARM_K=2` for the
   first A/B; raise to 3 only if that succeeds. Do not start at 4.
3. **Put LSP pregate and AST/lint into `swarm.screen`.** Today the screen is extract +
   compile + Black Tourmaline + dedup. Item 4's `ETHER_LSP_PREGATE` is a separate hook;
   it should also veto candidates *before* the single after-gate so K-1 extra after-runs
   are never spent. Same for an AST/lint critic.
4. **Add `ETHER_SWARM=record` (shadow).** Log `would_reject` / which candidate would have
   been picked, but still gate candidate 0 (or still gate the pick *and* record whether a
   rejected sibling would have been a keep — never a second keep, just a counterfactual
   log if a rejected candidate is later… no: do not run a second gate). Shadow the
   *prefilter* on a single candidate first, then enable K>1.
5. **Goal-flow scouts are not in item 5 and are the higher-ROI half of the ranking.**
   Without them, even BoN=4 still dries the 95-goal pool (~23 h idle in the 48 h sim).
   Add scout interleave in `goal_source.ranked` / `next_real` (prefer `test_import`, do
   not drain it to empty before touching SBFL; plant only when `selectable=0`). Item 0
   already exposes `selectable`.
6. **Telemetry into `learning_summary` and `first_hour_report`.** Item 5 writes
   `trace["swarm"]` (`k`, `valid`, `distinct`, `picked`, `why`, `secs`) on the attempt.
   Surface `model_calls`, `after_gate_skipped`, `swarm.k`, `swarm.valid`, `real_kept` vs
   `planted_kept`, and a **`filler_rate_real`** that does not include legacy filler keeps.
7. **`PRODUCT.md`.** `STATUS.md` leaves the wording open. Proposed line is in the next
   subsection. Do not implement `ETHER_SWARM_LIVE`.

### PRODUCT.md (still unchanged on `ether-batch10`; owner decision)

Today: "Not this product: a trading bot, a second writer, a swarm, port 8787."

Proposed: "One process on the 1650. `scripts/host_main.py` is the only writer; only the honest
gate keeps an edit. Matrix is the view. A swarm, if any, is a set of deterministic gem agents
and optional serial 4B samples inside that one process, one model call at a time. Not this
product: a trading bot, a second writer, a GPU-fan-out swarm, port 8787."

### Files already touched by item 5, and the follow-up

- Already: `core/agent/swarm.py` (`enabled`, `k`, `model_lock`, `serialized`, `screen`,
  `propose`), hook in `sota._attempt_real`, `tests/test_batch10_swarm.py`, FLAGS / BATCH10.
- Follow-up: extend `screen()` with LSP + AST/lint; add `mode()` in `{0, record, 1}` (keep
  `1` as today's K-proposer path); `goal_source.ranked` / `next_real` scouts; `outcome.metrics`
  + `first_hour_report`; `pillars.py` AST pregate. Do not route the real path through
  `gems.chain()` (still the five string rules). Do not weaken tests.

### Success / kill, measured on the 1650 via `first_hour_report`

**Phase A** (item 0 live, `ETHER_SWARM` left at 0, `ETHER_SAMPLE_TEMP=0,0.7`,
`ETHER_DEDUP_REPLY=1`, `ETHER_LSP_PREGATE=1` if pylsp/pyright is installed,
`ETHER_GEM_PREGATE=1`, `ETHER_PLANTED_GOALS=1` as dry-refill):

- Success: `real_graded` climbs past 238 within the first hour after apply (the queue is
  flowing); health never says "empty" when `real_queue.open>0`; `after_gate_skipped>0` once
  pregates are on; `kept_per_attempt` is not below 0.0084 beyond sampling noise; **zero**
  prefilter rejects that a shadow gate then *kept*.
- Kill / stay off: any would-reject that was a keep; or a clear drop in kept/attempt.

**Phase B** (`ETHER_SWARM=1`, `ETHER_SWARM_K=2`, only after Phase A is green for 6 h or 100
new real attempts):

- Success: real kept/attempt ≥ 1.5× the Phase A rate and real kept/GPU-hour not down more than
  10%.
- Kill: kept/GPU-hour drops, or `dup_share` stays ≥ 15% (diversity failed — fix temperature
  before raising K). Raise `ETHER_SWARM_K` to 3 only after BoN=2 is a success. Do not start at 4.

## 6. Simulation method (honest about assumptions)

`scripts/swarm_sim.py` (tests: `tests/test_swarm_sim.py`).

- **Live MLE via rates** are the default (`sbfl=0/133`, `test_import=2/87`, …). A keep is
  recorded only after an after-gate would run (honest-gate identity, tested).
- **Stated, not measured:** `T_MODEL=30`, `P_NO_EDIT=0.20`, `P_PRE_VETO=0.12`, `P_PRE_KILL=0.01`,
  `P_CRITIC_VETO=0.30`, `P_CRITIC_KILL=0.08`, `LOC_FRAC=0.15`, `P_PLANTED=0.08`, `DUP_TEMP=0.08`,
  `FLOW_SHARE` (70% test_import / 20% sbfl / …).
- **iid horizon** 238 and 1000 = infinite draws from the mix (or the reweighted mix).
- **pool** = 95 goals × 3 tries, 48 h wall; refill options run planted when the pool is dry
  (and, for the dedicated "planted" option, a 25% mix while it is open — shown in order to
  *discourage* that mix).
- **sparse** holds the mean p to the MLE but puts it on a small easy subset (p=0.30); BoN
  cannot unlock the rest.
- Seeds=200, seed 20261126. Re-run: `python scripts/swarm_sim.py --seeds 200`.

The MARL study's 0.107→0.131 kept/attempt and 10.1→6.5 kept/GPU-hour used *stated* p≈0.10 and
an 8 s guard, and are not overwritten here. They answered a different question (4B *roles* as
bandit arms). This study recalibrates to the live 0.0084 and the 245 s attempt.

----------------------------------------------------------------------------------------------------

## 7. Sources

Live host: `artifacts/learning_summary.json` generated 2026-11-26T17:47:48Z (real_graded 238,
real_passes 2, gpu_hours 14.903, dup_share 0.1846, by_via as above, filler_rate 0.9556 among
all kept including legacy, dry 160396 s). Batch 10 item 0 commit message on `20d0f617f2`.

Prior ETHER studies: `docs/MULTI_AGENT_RL.md`, `docs/RL_METHODS.md`, `docs/BANDITS.md`,
`docs/SELF_IMPROVE_ARCH.md`, `docs/FLAGS.md`. `scripts/rl_sim.py`, `scripts/bandit_sim.py`,
`docs/results/marl/marl_sim.py`.

Literature (arxiv ids previously fetched HTTP 200 from this environment on 2026-11-22 unless
noted): Chen et al., Codex / pass@k https://arxiv.org/abs/2107.03374 · Brown et al., Large
Language Monkeys https://arxiv.org/abs/2407.21787 · Wang et al., self-consistency
https://arxiv.org/abs/2203.11171 · Du et al., multi-agent debate https://arxiv.org/abs/2305.14325
· Together Computer, Mixture-of-Agents https://arxiv.org/abs/2406.04692 · Russo et al.,
Thompson sampling https://arxiv.org/abs/1707.02038 · Jimenez et al., SWE-bench
https://arxiv.org/abs/2310.06770 · Pan et al., SWE-Gym https://arxiv.org/abs/2412.21139.
MARL citations remain those in `docs/MULTI_AGENT_RL.md` §9.
