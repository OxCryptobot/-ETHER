# Bandits for ETHER self-improvement (batch 4, 2026-11-20)

Scope: how ETHER picks *what the 4B sees* for a real goal (failing test or lint), how
that choice learns from the honest gate, and what batch 4 ships. The gate is unchanged:
a goal is kept only when the tool edit makes its target test pass with 0 regressions in
the guard suite. Nothing in this document can turn a generation into a PASS.

## TL;DR

- The batch-2 learner (epsilon-greedy over 7 prompt arms) never ran on real goals: the live
  host still runs pre-batch-2 code, so `default` is the only arm that was ever pulled.
- With a few hundred graded pulls per bucket, **arm pruning is the biggest single win**:
  dropping `multifile` and `with_asserts` (they ask for output the one-function edit
  path cannot use) cuts simulated regret 13-32% for every selector (T=1000).
- **Default selector for real goals is now Beta-Bernoulli Thompson sampling with an
  empirical-Bayes prior over 5 arms** (`ETHER_BANDIT=thompson`). Over 5 synthetic scenarios
  at 1,000 pulls it has the best worst case (1.50x the best selector's regret vs 2.29x for
  the batch-2 path) and half the lock-in (23% vs 51% of runs end on a wrong arm).
  Honest trade-off: in the first ~200 pulls the batch-2 epsilon-greedy with pruned arms
  is better *when its built-in arm hints happen to be right*; see "Decision".
- **Promotion now needs P(arm beats incumbent) >= 0.9** under the 0/1 posteriors (plus the
  existing 3 honest passes). Wrong promotions drop 2-12x; first correct promotion comes
  later (median 116 vs 41 pulls in the mid scenario).
- Reward is the honest gate on a 0/1 scale: 1 = target passes **and** 0 regressions.
  Rule-based refactors no longer train the model arms (they did in batch 2/3).
- SBFL: hub demotion + logging-sink demotion + error-text tokens lift top-1 fault
  localisation on 66 seeded-mutant failures from 60.6% to 78.8%. With the new reply-size
  gate, the largest single SBFL target falls from 77% of SBFL goals (GemRegistry.execute)
  to 35%.
- Reply cap: batch 3 asked the 4B for at most 240 tokens, so 13 of 50 seed targets could
  never be written out in full. The cap now follows the target (240-768 tokens,
  `ETHER_REPLY_MAX`); 6 targets too big for any reply are dropped as `too_large`.

## 1. Inventory: what exists and what it actually does

Line numbers are at the batch-3 head (`e68b580dd`) unless marked (b4).

| Piece | Where | Algorithm / behaviour |
|---|---|---|
| `BanditPolicy` | `core/learning.py:215` (select `:296`, score `:285`, epsilon `:291`, update `:333`) | Contextual epsilon-greedy. Score = shrinkage mean `(R + 2*prior)/(n + 2)` (`PRIOR_WEIGHT` `:93`), prior = bucket mean + 0.15 hint bonus for hinted arms (`hinted_arms` `:168`). epsilon 0.15 annealed `eps/(1+n/25)`, floor 0.02; untried arms first ("cover"). Writes `memory/learning/bandit*.json` on every update and appends `experience.jsonl` (`append_experience` `:371`). |
| Arms | `STRATEGY_BEHAVIOUR` `core/learning.py:29` | 7 arms: `default`, `minimal`, `with_asserts`, `repair_heavy`, `no_context` (drops file slice), `repo_map_on` (signature map), `multifile` (asks for `# file:` blocks). Only `no_context`/`repo_map_on` change the context; `repair_heavy` adds a 2nd try (`core/agent/sota.py:423`); the rest add one prompt line. |
| Buckets | `context_key` `core/learning.py:157` | `phase|scope`: phase from fail kind (`gen` / `repair_syntax` / `repair_logic`), scope `complex` for tier >= 2. Real goals: `repair_logic|complex` (AssertionError) or `gen|complex`; lint `gen|simple`. One bandit file per goal kind (`outcome.bandit_path` `:37`). |
| Reward | `compute_reward` `core/learning.py:103`; `outcome.reward_for` `:181` | Honest pass -> 0.75 (holdout unknown cap), fail -> -0.9. Infra, "already present", "queue empty", "rejected" -> no update (`classify` `:170`). |
| Selection / logging | `outcome.choose` `:140`, `propensity_of` `:106`, `record` `:226` | Explore on for real goals (`explore_enabled` `:50`); else the promoted arm or `default`. Logs a trajectory per attempt with propensity (`trajectories.jsonl`, cap 2000 `MAX_TRAJ` `:29`). |
| Promotion | `outcome.maybe_promote` `:268` | >= 3 honest passes (`MIN_PASSES` `:26`), last pull a pass, score > incumbent + 0.05; demote after 3 straight fails. |
| Published view | `outcome.summary_doc` `:344`, `publish_summary` `:395`, called from `scripts/host_main.py:115-117` | `artifacts/learning_summary.json`, whitelisted fields, <= 16 KB. |
| Refactor arms | `core/agent/refactor.py:203` (`credit`), `:214` (`pick_strategy`) | Separate table `refactor_arms.json`, optimistic mean `(kept+1)/(pulls+2)`; deterministic, rule-based edits (96/97 kept in batch 2). |
| ES prototype | `core/agent/evolve_es.py:30/147/183` | (1+lambda)-ES over softmax logits fitted by SNIPS on logged propensities; off (`ETHER_NEURO_ES`). |
| Legacy ladder | `core/agent/learn.py:36` (`next_from`), `:247` (`score`) | Hand-written goal chain on `context_budget.py`; retired in batch 2 (`ETHER_SOTA_LEGACY=1` to restore). Not a learner. |
| Gem bag | `core/agent/gems.py:9` (`STAGE_GEM`), `:99` (`chain`) | Fixed stage -> gem routing; `chain` is a deterministic security/route/profile/memory/evolve pipeline. No choice is learned, so "gem choice" is not an arm today. |
| Pipeline bandit (old path) | `core/pipeline_select.py:21-39`, `core/loop/bandit_credit.py:8`, `gems/amethyst/evolution.py:27` | Same `BanditPolicy` used by the chat/pipeline path with `compute_reward`'s graded scale (confidence, verification, self-check). Not on the host's sota path. |
| Memory | `memory/learning/` (gitignored): `bandit*.json`, `trajectories.jsonl`, `promoted.json`, `experience.jsonl`; `memory/experience/*.jsonl` (`core/experience.py`) | Private state. Only `learning_summary.json` is published. |
| Fault localisation | `core/agent/fault_loc.py:95` (`ochiai`), `goal_source._sbfl_target` | Batch 3: Ochiai, min score 0.3. 24 of 31 SBFL goals pointed at `GemRegistry.execute`. |

What the live host actually did: `host_main.json` on origin (2026-11-20 11:18 ET) still
shows `plan_error: ImportError`, `next_goal: none`, `sota: queue empty`. The batch-2
audit found the bandit had only ever pulled `default` (`learn: arm default, reward 0.75,
promote hold`) on legacy filler goals. There is **no real-goal trajectory anywhere**, so
every number below comes from a calibrated simulator, not from the 1650.

## 2. Variants that fit a GTX 1650 + qwen3.5:4b

Every selector here is a few microseconds of CPU per decision; the GPU is spent only on
the 4B call. The constraint is data, not compute: one real attempt costs ~40-70 s (two
guard runs ~8 s, one 4B call, a second call for retry arms), and the queue holds ~50 goals
x 3 tries, so a bucket sees on the order of 100-1,000 graded pulls.

| Variant | Source | Fit for ETHER |
|---|---|---|
| epsilon-greedy (batch 2) | Lattimore & Szepesvari, *Bandit Algorithms*, ch. 6 — https://tor-lattimore.com/downloads/book/book.pdf | Cheap; good when its prior/hints are right; locks onto a wrong arm in ~50% of runs at these pass rates. |
| UCB1 | Auer, Cesa-Bianchi, Fischer 2002 — https://homes.di.unimi.it/~cesabian/Pubblicazioni/ml-02.pdf | Bonus `sqrt(2 ln N / n)` is large next to pass rates of 0.1-0.3, so it over-explores: worst adaptive selector here. |
| Thompson sampling (Beta-Bernoulli) | Russo et al., *A Tutorial on Thompson Sampling* — https://arxiv.org/abs/1707.02038 ; Chapelle & Li 2011 — https://papers.nips.cc/paper/2011/hash/e53a0a2978c28872a4505bdb51db06dc-Abstract.html ; Kaufmann et al. 2012 — https://arxiv.org/abs/1205.4217 | Natural for a 0/1 honest reward; randomised, so propensities exist for offline replay; best worst-case here. |
| Discounted TS / D-UCB | Raj & Kalyani 2017 — https://arxiv.org/abs/1707.09727 ; Garivier & Moulines 2008 — https://arxiv.org/abs/0805.3415 | Handles drift (easy goals consumed first). gamma = 0.98 forgets too fast at these rates (regret +20-113% at T=1000, even in the drift scenario); ship gamma = 1, revisit with measured drift. |
| Contextual: LinUCB / per-context TS | Li et al. 2010 — https://arxiv.org/abs/1003.0146 ; Agrawal & Goyal 2013 — https://arxiv.org/abs/1209.3352 | 7 features (`bandit.FEATURES`: assert, via sbfl/frame, lint, retried, tractability). Wins clearly only when the best arm depends on the goal (contextual scenario: 35.9-37.7 vs 53.6); loses elsewhere by splitting data. Ship as opt-in. |
| Cost-aware (pass per GPU-second) | Xia et al. 2015, *Thompson Sampling for Budgeted MAB* — https://arxiv.org/abs/1505.00146 | +8-14% kept per GPU-hour, but fewer kept per attempt. Today goals (not GPU time) are the scarce resource, so off by default. |
| Factored / combinatorial arms | Chen, Wang, Yuan 2013 — https://proceedings.mlr.press/v28/chen13a.html | One posterior per factor level (style, context slice, retry) instead of one per combo: 46.7 vs 71.5 regret over 18 combos. Opt-in. |
| Best-arm identification for promotion | Russo 2016 — https://arxiv.org/abs/1602.08448 ; prompt selection as BAI: Shi et al. 2024 — https://arxiv.org/abs/2402.09723 | Basis for the posterior promotion rule. |
| Offline replay | Li et al. 2011 — https://arxiv.org/abs/1003.5956 | `scripts/bandit_sim.py --replay` gives raw and IPS pass rates per arm; `snips()` values a policy from logged propensities (tested to +-0.04). |

All URLs were checked to return HTTP 200 on 2026-11-20.

## 3. Offline evaluation (`scripts/bandit_sim.py`)

The simulator calls the shipped selector code (`core.agent.bandit.select/update`,
`lin_score/lin_update`, `factored_select`) plus an exact port of `BanditPolicy`
(0.75/-0.9 reward, prior weight 2, epsilon anneal, `repair_logic|complex` hints). Fixed seeds;
`python scripts/bandit_sim.py --seeds 200 --out docs/results/batch4/bandit_sim.json`
(651 s on the box, 5 processes). Full tables: `docs/results/batch4/bandit_sim.md`.

Calibration (stated assumptions, because the host never ran a real goal):
- goal mix from `config/goal_seed.json`: 31 sbfl, 19 test_import, 1 frame, 4 lint;
- cost: 8 s guard + 30 s per 4B call (no_context 0.7x, repo map 1.1x); a retry arm pays a second call + gate when the first try fails; retry success = 0.6 x first-try rate;
- per-try honest pass rates: **low** (default 0.10, best arm 0.13), **mid** (x2.5),
  **unhinted** (best arm `minimal`, which batch-2 hints do not favour), **contextual**
  (best arm depends on via: sbfl -> repo map, test_import -> default, lint -> minimal),
  **drift** (mid for the first half, then rates fall and the best arm changes).

Regret = expected honest passes lost against always choosing the best arm for that goal.

**T = 200 graded pulls** — mean regret (lost honest passes vs always picking the best arm), 200 seeds; worst = max over scenarios of regret / best regret in that scenario; lock = share of runs whose most-pulled arm in the last quarter is not the best

| selector | low | mid | unhinted | contextual | drift | worst | lock (avg) |
|---|---|---|---|---|---|---|---|
| egreedy-7 (batch-2 live) | 6.1 | 12.1 | 13.0 | 12.8 | 12.2 | 1.59x | 0.58 |
| egreedy-5 | 3.8 | 8.3 | 11.9 | 9.9 | 9.4 | 1.26x | 0.52 |
| thompson-5 **(batch-4 default)** | 6.9 | 12.4 | 9.5 | 12.1 | 11.3 | 1.81x | 0.45 |
| thompson-5 beta(1,1) | 7.4 | 12.0 | 10.9 | 12.8 | 11.2 | 1.94x | 0.43 |
| thompson-7 | 9.0 | 16.1 | 11.8 | 15.2 | 14.7 | 2.36x | 0.45 |
| ucb1-5 | 9.1 | 16.5 | 13.2 | 14.1 | 13.5 | 2.39x | 0.47 |
| thompson-5 g=0.98 | 7.8 | 14.6 | 11.2 | 13.2 | 11.9 | 2.04x | 0.48 |
| thompson-5 cost | 9.3 | 18.3 | 9.4 | 13.9 | 15.1 | 2.43x | 0.74 |
| thompson-5 by-via | 7.8 | 15.1 | 11.3 | 11.0 | 12.8 | 2.04x | 0.48 |
| linucb-5 | 8.1 | 12.8 | 11.2 | 11.6 | 11.4 | 2.12x | 0.46 |
| uniform-5 | 10.2 | 22.0 | 15.1 | 15.1 | 16.8 | 2.69x | 0.76 |

**T = 1000 graded pulls** — mean regret (lost honest passes vs always picking the best arm), 200 seeds; worst = max over scenarios of regret / best regret in that scenario; lock = share of runs whose most-pulled arm in the last quarter is not the best

| selector | low | mid | unhinted | contextual | drift | worst | lock (avg) |
|---|---|---|---|---|---|---|---|
| egreedy-7 (batch-2 live) | 21.4 | 38.1 | 51.7 | 56.0 | 46.0 | 2.29x | 0.51 |
| egreedy-5 | 14.6 | 27.5 | 44.7 | 47.9 | 38.7 | 1.98x | 0.43 |
| thompson-5 **(batch-4 default)** | 21.9 | 32.2 | 26.2 | 53.6 | 39.2 | 1.50x | 0.23 |
| thompson-5 beta(1,1) | 23.3 | 31.7 | 29.3 | 55.4 | 37.8 | 1.60x | 0.20 |
| thompson-7 | 28.1 | 41.4 | 33.5 | 61.7 | 47.7 | 1.92x | 0.25 |
| ucb1-5 | 40.8 | 62.9 | 56.7 | 66.2 | 56.2 | 2.79x | 0.24 |
| thompson-5 g=0.98 | 36.8 | 68.6 | 52.7 | 64.3 | 52.5 | 2.52x | 0.34 |
| thompson-5 cost | 41.0 | 72.0 | 22.6 | 65.3 | 69.2 | 2.81x | 0.73 |
| thompson-5 by-via | 27.9 | 48.2 | 38.5 | 35.9 | 48.3 | 1.91x | 0.33 |
| linucb-5 | 30.6 | 36.7 | 37.1 | 37.7 | 41.5 | 2.09x | 0.32 |
| uniform-5 | 51.1 | 109.8 | 75.1 | 75.5 | 83.4 | 3.99x | 0.74 |

**kept per attempt / kept per GPU-hour, T=1000**

| selector | low | mid | unhinted | contextual | drift |
|---|---|---|---|---|---|
| egreedy-7 (batch-2 live) | 0.133 / 8.8 | 0.326 / 22.8 | 0.148 / 12.0 | 0.148 / 10.8 | 0.216 / 14.9 |
| thompson-5 | 0.131 / 8.8 | 0.329 / 22.3 | 0.174 / 15.2 | 0.150 / 10.8 | 0.221 / 14.9 |
| thompson-5 cost | 0.111 / 9.5 | 0.290 / 25.4 | 0.178 / 16.6 | 0.139 / 12.3 | 0.191 / 16.6 |
| uniform-5 | 0.102 / 8.6 | 0.253 / 21.8 | 0.125 / 10.4 | 0.128 / 10.8 | 0.178 / 15.1 |

**Promotion, T=1000, thompson-5 selector** (correct promotion by T / median pull of first correct promotion / promotions of an arm worse than `default` per run)

| rule | low | mid | unhinted | contextual | drift |
|---|---|---|---|---|---|
| batch-2 score rule | 0.89 / 74 / 3.81 | 0.95 / 41 / 4.38 | 0.94 / 51 / 7.13 | 0.88 / 69 / 6.34 | 0.96 / 27 / 16.17 |
| batch-4 posterior rule (default) | 0.80 / 263 / 0.32 | 0.93 / 116 / 1.04 | 0.84 / 174 / 0.90 | 0.67 / 259 / 1.45 | 0.85 / 81 / 8.34 |

**Factored arms (18 combos = 3 styles x 3 context slices x 2 retry policies)**

| selector | regret T=200 | regret T=1000 | kept/attempt T=1000 |
|---|---|---|---|
| egreedy-18 | 17.2 | 68.9 | 0.182 |
| thompson factored | 16.9 | 46.7 | 0.205 |
| thompson-18 flat | 20.6 | 71.5 | 0.181 |
| uniform-18 | 25.6 | 128.1 | 0.124 |

### Decision

- **Thompson-5 with a pooled prior is the default** (`ETHER_BANDIT` unset). Reasons: lowest
  worst-case regret at 1,000 pulls (1.50x vs 2.29x for batch 2), lowest lock-in, best in the
  scenario where the batch-2 hints are wrong (26.2 vs 51.7), and propensities for offline
  replay. The pooled prior (2 pseudo-pulls at the bucket's pass rate) beats Beta(1,1)
  in 3 of 5 scenarios at both horizons (the other two are within noise).
- **What it costs**: at 200 pulls, epsilon-greedy over the same 5 arms loses fewer passes in
  the 4 scenarios where its hints (`repair_heavy`, `repo_map_on`) are the good arms (3.8 vs
  6.9 in "low"). That is ~1-3 kept edits in the first day, and it rests on a guess nobody
  has measured. `ETHER_BANDIT=egreedy` restores batch-2 selection exactly (7 arms, same code);
  add `ETHER_PROMOTE_RULE=score` for batch-2 promotion too.
- **Promotion**: the posterior rule (`ETHER_PROMOTE_RULE=posterior`, default for real
  kinds) is slower but makes 2-12x fewer wrong promotions; `score` restores batch 2. In the
  drift scenario both rules still count early promotions that became wrong after the shift.

## 4. Arm design

Shipped (b4): `REAL_ARMS = default, minimal, repair_heavy, no_context, repo_map_on`
(`core/agent/bandit.py`), override with `ETHER_BANDIT_ARMS`. Each changes what the 4B sees:
nothing / a terse-style line / one retry with the failure / no file slice / signature map.

Factored option (`ETHER_BANDIT_FACTORED=1`): arm `f:<style>.<ctx>.<retry>` with style in
{plain, minimal, defensive}, ctx in {file, none, map}, retry in {1, 2}; one Beta posterior per
level, chosen independently (`factored_select`), mapped to a real `ArmBehaviour`
(`factored_behaviour`) and retry count (`tries_for`). Adding a factor (e.g. tool sequence
"search first" vs "edit directly", or patch scope "function" vs "function + constants")
adds 2-3 posteriors instead of multiplying the arm count.

Hierarchy that avoids combinatorial blowup:
1. goal kind (separate state files: `bandit4_fix_test.json`, `bandit4_lint.json`);
2. bucket (`context_key`: assert vs other error);
3. arm (flat 5) or factors (3 x 3 x 2);
4. contextual features only when the published `metrics.by_via` table shows the pass rate
   differs by localisation route.
Refactor strategies (`remove_filler`, `dead_code`, `ruff_safe`) stay on their own
rule-based table: they make no model call, so they must not move model arms.

Not arms (today): gem choice (the gem bag is a fixed route, `gems.STAGE_GEM`), and
whole-file rewrites (the gate edits functions and constants only).

## 5. Reward and reward hacking

- `outcome.reward01` (b4 `core/agent/outcome.py:205`): 1 only if the gate returned
  `tests_ok` **and** `regressions == 0`; every other model outcome (no function in the
  reply, no edit, target still failing, siblings failing, regression reverted) is 0.
  Infra outages, "already present", "queue empty" and quality-guard rejections are
  not model outcomes and update nothing (tested).
- The legacy 0.75 / -0.9 scale is still written to `BanditPolicy` so `ETHER_BANDIT=egreedy`
  resumes with warm state.
- No partial credit from model self-claims: `ok` without the gate's `tests_ok` is a fail
  (tested); generate-only is never a pass.
- Cheats: an edit must pass every related failing test in the same file (batch 3
  sibling rule) and keep every passing test passing (batch 2 regression guard). Both
  outcomes land as reward 0, so a cheating style cannot earn promotion.
- Batch 2/3 bug closed: rule-based refactor results (`policy: tool`) were classified as
  model passes and trained `bandit_refactor.json`; they are now `kind: tool` and only
  credit the refactor strategy table.

## 6. Fault localisation and reply size (cheap fixes that raise the pass ceiling)

`docs/results/batch4/sbfl_bench.py` (scratch copies only):

| | Ochiai (batch 3) | hub-aware rank (b4) |
|---|---|---|
| Seeded mutants: failing tests on the SBFL path | 66 (40 mutants of 123 tried) | 66 |
| top-1 = mutated function | 60.6% | **78.8%** |
| top-3 | 87.9% | 86.4% |
| found above the 0.3 threshold | 95.5% | 97.0% |
| mean rank when found | 2.56 | 1.91 |

Live failing set (74 failures, same scan):

| | Ochiai (b3) | hub rank, no size gate | hub rank + reply-size gate (b4) |
|---|---|---|---|
| goals | 51 | 51 | 45 (+6 `too_large` drops) |
| distinct SBFL targets | 4 | 7 | 10 |
| largest SBFL target share | 77% `GemRegistry.execute` | 58% `Pipeline.run` | 35% `GemRegistry.execute` |
| targets too long for a 240-token reply | 13 | 35 | 8 (reply cap now scales) |
| targets too long for any reply (768) | 6 | 27 | 0 |

`fault_loc.rank`: Ochiai x (1 - 0.6 x share of passing tests that run the function),
x 0.25 for logging sinks (`_log`, `warn`, `emit`, ...), + 0.2 x name tokens shared with the
error text / test source. `ETHER_SBFL_RANK=ochiai` restores batch 3. The hub rank alone
moved 18 goals onto `Pipeline.run`, a 220-line function no 4B reply can rewrite; the size
gate skips such suspects. Remaining honest limit: `GemRegistry.execute` still takes 11
goals; a 1-call dispatcher is a likely *wrong* target for most of them (next step 3).

Reply cap: `goal_source.reply_tokens` = 1.25 x the target's estimated tokens + 64,
clamped to 240..`ETHER_REPLY_MAX` (768); `react(..., n=)` passes it to Ollama `num_predict`.
On the 1650, a 768-token reply is ~25-30 s of decode, and the 4B stops at the end of the
function, so cost follows the target size. The prompt budget (35% of ctx, <= 1,800
tokens) leaves room in a 4K-8K context.

## 7. Metrics (published in `artifacts/learning_summary.json`, schema 2)

`metrics` (from honest-gate trajectories, real goal kinds only):
`attempts`, `kept`, `kept_per_attempt`, `gpu_hours` (wall seconds of graded attempts),
`kept_per_gpu_hour`, `sessions` (last 7 UTC days: attempts, kept), `kept_per_session`,
`filler_rate` (kept goals with filler ids; must stay 0), `revert_rate` (edits the gate
reverted: regression / tests failed / siblings failed), `regressions_caught`,
`promotions`, `demotions` (`memory/learning/promotions.jsonl`, cap 200), `arm_entropy_bits`
per kind, `tool_edits` (rule-based refactors), `by_via` (attempts / kept per localisation
route).
`bandit`: selector per kind, gamma, cost/factored flags, arm list, and per bucket the pulls,
passes, posterior mean, seconds per pull, P(best) and entropy per arm.
Trajectory rows gain `reward01`, `secs`, `algo`, `note`, `via`, `reply_cap`.

Targets for the first live day on the 1650: filler_rate 0; kept_per_attempt > 0 for real
goals (any kept edit is a genuine repair); revert_rate and regressions_caught reported;
arm entropy > 1.5 bits for the first ~100 pulls, then falling as one arm wins.

## 8. Flags (all env, read per call)

| Flag | Default | Effect |
|---|---|---|
| `ETHER_BANDIT` | `thompson` | `thompson`, `ucb`, `linucb`, or `egreedy` (= batch-2 selection, 7 arms; pair with `ETHER_PROMOTE_RULE=score` for full batch-2 behaviour). Real goals only; legacy and refactor stay on batch-2 behaviour. |
| `ETHER_BANDIT_ARMS` | 5 real arms | comma list of `STRATEGY_BEHAVIOUR` names |
| `ETHER_BANDIT_GAMMA` | `1.0` | discount for drift (0.5-1.0) |
| `ETHER_BANDIT_COST` | `0` | `1` = pick by sampled pass rate per second |
| `ETHER_BANDIT_FACTORED` | `0` | `1` = style x context x retry factors |
| `ETHER_PROMOTE_RULE` | `posterior` | `score` = batch-2 rule |
| `ETHER_SBFL_RANK` | `hub` | `ochiai` = batch 3 |
| `ETHER_REPLY_MAX` | `768` | max reply tokens for a real-goal edit; targets above it are dropped |
| `ETHER_SOTA_EXPLORE` | on for real goals | `0` = promoted arm or `default` only (unchanged) |

State: `memory/learning/bandit4_<kind>.json` through `core.spine.state_io.write_json`
(single writer, D3-clean), <= 24 buckets, allowed arms only.

## 9. Integration with the ladder, gem bag and memory

- learn.py ladder: retired; legacy goals keep the batch-2 selector, so nothing changes
  if `ETHER_SOTA_LEGACY=1` is set again.
- Gem bag: no learnable choice today. If a stage ever gets two real implementations
  (e.g. two context packers), add it as a factor, not as new flat arms.
- Memory: bandit state, trajectories and promotions stay private in `memory/learning/`;
  the published summary is numbers and whitelisted ids only. `experience.jsonl`
  re-injection (few-shot) is untouched; the `no_context` arm is the ablation that tells
  whether it helps.
- Neuroevolution (`evolve_es`, off) can now use the logged Thompson propensities for its
  SNIPS fitness; MAP-Elites over factor levels is the natural next experiment.

## 10. Ranked next steps (measured)

1. **Get the code live** (batch 2+3+4 bundle). Until then every number here is simulated.
   Measure on the first 100 real pulls: kept_per_attempt, revert_rate, by_via, arm entropy.
2. **Recalibrate the simulator from real trajectories** (`--replay`), re-run the
   comparison, and re-decide `ETHER_BANDIT` / `ETHER_PROMOTE_RULE` with real pass rates.
3. **Dispatcher targets**: `GemRegistry.execute` still holds 11 SBFL goals. Add a
   one-hop "callee of the dispatcher" step (the gem handler the failing test reaches) and
   measure top-1 on the mutant bench plus kept/attempt per via.
4. **Turn on per-via context** (`linucb` or per-via buckets) only if `by_via` pass rates
   differ by > 2x after ~300 pulls (the contextual scenario says it would then cut regret ~33%).
5. **Factored arms with a tool-sequence factor** ("search first" vs "edit directly") once
   the flat arms are measured; the simulator says factoring beats a flat 18-arm set by ~35%.
6. **Cost-aware selection** when goal supply stops being the limit (continuous rescans
   + refactor kind on): +8-14% kept per GPU-hour in simulation.
7. **Drift check**: compare pass rates in the first and second half of each week; enable
   `ETHER_BANDIT_GAMMA=0.995` only if they differ.
