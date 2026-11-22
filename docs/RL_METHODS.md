# RL methods for ETHER self-improvement (batch 8 study, 2026-11-22)

Project ETHER only. Doctrine unchanged: single writer `scripts/host_main.py`, Matrix read-only, tool-first,
**honest gate only** (a goal is kept only when the tool edit makes its target and siblings pass with 0
regressions, `core/agent/goal_source.py:1264` `gate`, `:1244` `regressions`, `:1248` `siblings`,
`:1233` `guard_suite`), no generate-fallback as PASS, GTX 1650 + qwen3.5:4b, **no weight training on the host**.
Line numbers are for branch `ether-batch8-rl` (base `ether-batch7` c8003135c9). Companion to
`docs/SELF_IMPROVE_ARCH.md` (batch-7 architecture study) and `docs/BANDITS.md` (batch 4).

All "sim" numbers below are **SIMULATION** (assumed pass rates over the 60 real seed goals), not host data.
The host has not run batch 2–7 code yet; Phase 0 (`ETHER_EXEMPLARS=record` + `scripts/first_hour_report.py`)
produces the first real numbers.

## TL;DR

1. **The arm learner is not the bottleneck.** In the finite-pool sim, every arm selector (TS, discounted TS,
   sliding-window TS, per-via TS, hierarchical TS, LinUCB 7 / 9 features, uniform) lands within ~0.5–1.0 kept
   of each other per pool (e.g. mid: TS 14.87 ± 0.32, LinUCB-9f 15.13 ± 0.30, uniform 14.41 ± 0.30). Keep the
   bundle's TS; do not build fuller contextual/hierarchical bandits before host data shows per-via differences.
2. **Goal selection: keep the live `ranked` order** (`goal_source.py:859`). It is best or tied on total kept
   and best on kept@60 attempts (mid 9.09 vs goal-TS 8.57, breadth 8.39, random 7.47) and first keep.
   A goal-selection/curriculum bandit is not worth building now.
3. **Sampling temperature by try index is the only lever with a clear sim gain**: "0 then 0.7" vs greedy
   T=0: low 7.52 vs 6.61, mid 16.15 vs 14.87, contextual 16.45 vs 15.30, drift 15.70 vs 14.46 kept per pool.
   The gain **depends on the duplicate-reply rate** (sim assumption DUP=0.8); with DUP=0.3 it shrinks to
   +0.07 (low) / +0.24 (mid), inside the ±95% band. So it is measured first, decided second.
   **Prototyped flag-off in this branch** (`ETHER_SAMPLE_TEMP`, `ETHER_DEDUP_REPLY`, always-on
   duplicate-reply logging for Phase 0).
4. Preference learning (DPO/ORPO/KTO) is **not feasible on the host and not data-feasible yet**: the whole
   pool yields at most ~60 kept goals × ≤2 reverted siblings ≈ ≤120 within-goal pairs; published DPO runs use
   thousands. Use the pairs for a **test-only reranker / Bradley-Terry diagnostics**, not training.
5. Reward stays the gate's 0/1 per attempt (`outcome.py:205` `reward01`). No partial credit as reward.

### Correction to the architecture study

`docs/SELF_IMPROVE_ARCH.md` said "60 goals × ≤6 tries ≈ 360 attempt slots" and "the goal's 6 tries".
The code says **`MAX_TRIES = 3` per goal** (`goal_source.py:878`) and **`MAX_TARGET_TRIES = 6` per SBFL
target** (`:879`), and a keep resolves the siblings on the same target. In the sim that gives a pool of
**~133–151 graded attempts**, not 360. This makes every A/B ~2.5× more expensive in pools (§6) — at 60
attempts/h a pool lasts ~2.2–2.5 h, not ~6 h. That doc is corrected in this branch.

## 0. Inventory (what exists, file:line)

| piece | where | notes |
|---|---|---|
| reward | `core/agent/outcome.py:205` `reward01`, `:215` `classify`, `:273` `record` (logs propensity) | 0/1 from the gate; rejected/infra rows are not graded |
| promotion | `outcome.py:383` `maybe_promote` (posterior P≥0.9, `MIN_PASSES=3` at `:26`) | |
| arms | `core/agent/bandit.py:41` `REAL_ARMS` = default, minimal, repair_heavy, no_context, repo_map_on (+`exemplar` arm with `ETHER_EXEMPLARS=1`, `:97`) | |
| selectors | `bandit.py:130` TS draws (pooled prior `PRIOR_N=2`, `:54`), UCB, ε-greedy, LinUCB; `:256` `features` (7: bias, assert, sbfl, frame, lint, retried, tractability); `:352` `choose`, `:389` `record`, `:190` `update` | |
| non-stationary | `ETHER_BANDIT_GAMMA` (`bandit.py:72`) = discounted TS / D-UCB | default 1.0 |
| cost-aware | `ETHER_BANDIT_COST=1` (`bandit.py:79`) θ / mean_secs (Xia et al. 2015) | |
| factored arms | `ETHER_BANDIT_FACTORED=1` (`bandit.py:83`) | |
| retries | `bandit.py:308` `tries_for` (repair_heavy = 2 inner tries) | |
| goal order | `goal_source.py:859` `ranked` = tractability − 0.2·own tries − 0.1·shared; `:696` `tractability`; `:882` `next_real`; `:902` `mark` | |
| prompt | `goal_source.py:955` `build_prompt` (+ exemplars, `core/agent/exemplars.py`) | |
| attempt loop | `core/agent/sota.py:409` `_attempt_real`; `:383` `_one` (choose → attempt → record); gate call `:525` | |
| sampling | `scripts/host_main.py:145-147` `_code` → `scripts/live_edit_tx.py:27,38` `_ask(..., temperature=0)` | **all real-goal replies greedy**. Precedent: the legacy tx loop already retries at T=0.3/0.4 (`live_edit_tx.py:172,199,247,251`) |
| gems | `core/agent/gems.py` route `:40`, memory `:49`, profile `:60`, security `:69`, evolve `:78`, fabricate `:89`, chain `:99` | safety / format rules |
| metrics | `outcome.py:488` `metrics` (attempts, kept, kept/attempt, gpu_hours, kept/GPU-h, filler_rate, revert_rate, regressions_caught, arm_entropy_bits, by_via; batch 8: dup_share, by_temp), `:556` `summary_doc` → `learning_summary.json`; `:466` `_SAFE_FIELDS` | |
| report | `scripts/first_hour_report.py:64` `learning_view`, `:132` `render` | |

Seed pool (`config/goal_seed.json`): 60 goals (56 fix_test, 4 lint); via: sbfl 35, test_import 19, none 4,
import_error 1, test_import_assign 1; 11 span goals; 38 targets, 15 shared, max 7 goals on one target;
tractability 0–0.77, median ≈0.23.

## 1. Bandits: what is in the bundle vs fuller variants

| variant | in bundle? | sim result (kept per pool, mid / contextual / drift / low) | verdict |
|---|---|---|---|
| Beta-Bernoulli TS, pooled prior (live) | yes | 14.87 / 15.30 / 14.46 / 6.61 | keep as default |
| discounted TS γ=0.98 | yes (`ETHER_BANDIT_GAMMA`) | 14.79 / 15.09 / 14.61 / 6.85 | no gain even with an arm-effect switch at attempt 60 |
| discounted TS γ=0.995 | yes | 14.90 / 15.11 / 14.59 / 6.78 | same |
| sliding-window TS W=60 | no (sim only) | 14.72 / 15.13 / 14.68 / 6.60 | not worth adding |
| TS per via (contextual by bucket) | sim | 14.55 / 15.28 / 14.29 / 6.57 | splits too little data |
| hierarchical TS (via → kind → global prior) | sim | 14.78 / 15.56 / 14.57 / 6.78 | +0.26 only when contexts truly differ |
| LinUCB 7 features | yes | 14.82 / 15.56 / 14.66 / 6.83 | ≈ hier TS |
| LinUCB 9 features (+span, retry index, exemplar-eligible) | sim | 15.13 / 15.44 / 14.85 / 6.87 | best kept/GPU-h (mid 11.33 vs TS 10.49) because it spreads arms → fewer duplicates |
| uniform | — | 14.41 / 14.58 / 14.21 / 6.55 | floor |
| cost-aware TS | yes (`ETHER_BANDIT_COST`) | bandit_sim regret: low 9.27, mid 18.34 vs TS 6.88 / 12.37 | lower kept/attempt; only if GPU time, not attempts, is the binding limit |

Earlier infinite-horizon regret sim (`scripts/bandit_sim.py`, 200 seeds, `docs/results/batch8/bandit_sim_T200.json`):
low TS 6.88, LinUCB 8.09, γ0.98 7.76, ε-greedy-5 3.81, uniform 10.24; contextual by-via 10.98, LinUCB 11.58,
TS 12.05. (ε-greedy-5 is low only because that sim's arms are close; it is not a reason to switch.)

Why selectors barely matter: ~134–150 graded attempts per pool, 5 arms, effects of ±0.2–0.9 logits. The pool
ends before any selector can exploit much. Sources: Russo et al. TS tutorial; Raj & Kalyani dTS; Garivier &
Moulines D-UCB; Li et al. LinUCB; Agrawal & Goyal linear TS; Xia et al. budgeted TS.

## 2. Outcome-based RL with honest-gate-only reward

- **Reward = per-attempt 0/1 from the gate** (current). Per-goal reward (kept within 3 tries) is for reporting
  only: it mixes arms across retries and hides which pull worked.
- **Credit assignment across retries:** each graded attempt is its own bandit pull with its own arm; the
  attempt index is already context (`features` "retried"). Later attempts see harder residual goals, so the
  raw pass rate by try index is confounded — compare arms *within* a try index (by_temp/by-try split), never
  across.
- **Reward shaping:** potential-based shaping (Ng et al. 1999) preserves the optimal policy but needs a
  potential; any "partial credit" (fewer failing asserts, compiles, sibling passes) **may not enter the reward**:
  it is gameable (edit the assert message, delete a branch) and would reward non-kept edits. Allowed uses:
  features, goal ordering (already via tractability), and feedback text for the next try.
- Duplicate replies: a byte-identical edit on identical file + guard-baseline state gets the same gate verdict;
  `ETHER_DEDUP_REPLY=1` (batch 8) reuses that verdict instead of re-running the tests (reward 0, note
  "duplicate reply"). It can only *withhold* a keep, never grant one.

## 3. Preference / ranking over trajectories

- Pairs: within one goal, a kept edit vs that goal's reverted edits controls for goal difficulty
  (conditional logit / Bradley-Terry with goal fixed effects). Max pool yield ≈ 60 kept × ≤2 reverted ≈ **≤120
  pairs** (MAX_TRIES=3), realistic ≈ sim kept 7–16 per pool → ≤14–32 pairs per pool.
- **Bradley-Terry / Elo over arms or exemplars:** fine as a diagnostic; with ≤32 pairs per pool it does not
  beat the Beta posteriors already in `bandit.py`.
- **Test-only reranker:** with k sampled candidates per attempt, rank by "gate passes", i.e. run the gate on
  each — that *is* the honest gate (best-of-k with verification, Large Language Monkeys). Cost is k model calls
  + up to k gate runs per attempt; only after Phase 1 shows sampled replies differ. A learned reranker (score
  without running tests) may only *order* candidates; the gate still decides.
- **DPO / ORPO / KTO:** need a policy update → **off-box only** (doctrine: no weight training on the host;
  1650 has 4 GB, ~2.7 GB in use by the 4B). QLoRA (Dettmers et al.) of a 4B model is an off-box job on a
  ≥16 GB GPU (**estimate**, not measured). Data: DPO/ORPO papers train on thousands to tens of thousands of
  pairs; ≤120 pairs is far below that. KTO accepts unpaired 0/1 labels (every graded attempt), which is the
  better fit if it is ever tried. SWE-Gym (Pan et al.) shows fine-tuning on verified agent trajectories helps,
  with hundreds of trajectories. Verdict: **log now** (trajectories already carry reply_hash/goal/reward), train
  never on the host, revisit off-box at ≥1–2k graded attempts.

## 4. Lightweight methods

| method | sim / evidence | cost | verdict |
|---|---|---|---|
| **temperature by try index** (`ETHER_SAMPLE_TEMP=0,0.7`) | sim +0.9 to +1.3 kept/pool at DUP 0.8; +0.07/+0.24 at DUP 0.3; T=0.7 always is *worse* than T=0 at DUP 0.3 (low 7.18 vs 7.45) | 0 extra calls | **prototype (this branch)**; decide from Phase-0 dup_share |
| temperature bandit {0, .4, .8} | sim ≈ schedule (mid 16.06 vs 16.15) | small | not needed over the schedule |
| combinatorial prompt-component bandit (Chen et al. 2013) | = `ETHER_BANDIT_FACTORED` | exists | only with ≥1 pool per component pair |
| exemplar utility ranking | Beta lift per exemplar (kept with / shown) × similarity | small | after Phase 0 shows ≥10 exemplar-eligible keeps |
| goal-selection / curriculum bandit (learning progress, Graves et al. 2017) | sim: ranked wins (kept@60 mid 9.09 vs goal-TS 8.57) | medium | **don't build** |
| gem-decision bandit over gems.py rules | — | — | **don't learn safety/format rules** (security `:69`, fabricate `:89`); at most a tools-on/off (react turns) arm |
| self-consistency / majority vote over edits (Wang et al.) | — | k calls | weaker than best-of-k with the gate |
| prompt best-arm identification (Shi et al. 2024) | — | — | fits offline prompt search; pool too small online |

## 5. Integration and anti-reward-hacking

- All flags default off; with them unset prompts, calls and decisions are byte-identical (tests in
  `tests/test_batch8_sampling.py`).
- Batch-8 hooks: `core/agent/sampling.py` (schedule, `with_temp`, `edit_hash`, `file_hash`, `reverted_before`);
  `sota.py:470,490-493` (temperature per try index), `:511-519` (hashes + optional dedup) ; `sota.py:354`
  `_guard` forwards kwargs and records whether the real ask takes a temperature (test mocks without it keep
  working); `host_main.py:145-147` `_code(..., temperature=0.0)`; `outcome.record` adds `reply_hash`,
  `file_hash`, `temp`, `dup`; `metrics` adds `dup_share`, `by_temp` (→ `learning_summary.json`);
  `first_hour_report` prints "duplicate replies … kept by temperature …".
- Anti-hacking: the gate is the only reward; protected paths stay refused by `apply_edit`
  (`goal_source.py:1142`); siblings + guard suite catch "pass the target, break the rest"; dedup can only
  convert a would-be gate run into the same 0; watch revert_rate and regressions_caught per temperature;
  temperature capped at 1.2 (`sampling.MAX_TEMP`); higher-T replies that pass weak tests show up as a revert
  rate or a later regression → stop rule below.

## 6. Measurement

Power table (attempts per arm; one-sided α 0.10 ≈ P≥0.9, power 0.8 / two-sided α 0.05): 0.05→0.15: 79 / 138;
0.10→0.25: 56 / 97; 0.10→0.20: 113 / 197; 0.20→0.30: 167 / 291; 0.10→0.15: 393 / 683.

With ~134–150 attempts per pool, a two-arm A/B at kept/attempt resolves only big effects (≥ +10–15 points)
in one pool. The sim's temperature gain is +1 point of kept/attempt (mid 0.111 → 0.121): **not detectable
by a kept/attempt A/B** in any reasonable number of pools. Measure it through its mechanism instead:

| option | primary metric | design | data needed | accept if |
|---|---|---|---|---|
| temperature schedule | (a) `dup_share` at T=0 (Phase 0); (b) pass rate of retry attempts (try ≥1) by temp | Phase 0 T=0 baseline, then one pool with `ETHER_SAMPLE_TEMP=0,0.7` | (a) one pool; (b) ≥56 retry attempts per side for 0.10→0.25 | (a) dup_share ≥0.15 → turn on; (b) retry pass rate not lower, revert_rate and regressions_caught not higher |
| dedup | gate runs saved, kept unchanged | on in the same pool | 1 pool | 0 keeps lost (dedup can't keep), CPU s saved > 0 |
| LinUCB-9f / hier TS | kept/GPU-h | only if Phase 0 by_via shows ≥0.10 pass-rate spread | ≥2 pools | P(better) ≥0.9 |
| exemplar ranking | kept/attempt with vs without exemplar on eligible goals | `ETHER_EXEMPLARS=1` arm | 0.05→0.15: 79/arm | P≥0.9 |
| goal curriculum | kept@60 | — | — | not planned |

Always report: kept, revert_rate, filler_rate, arm_entropy_bits, regressions_caught, dup_share, by_temp.

## 7. Ranking (gain / cost / risk)

1. Duplicate-reply logging (always on, measurement only) — needed for every decision below; cost ~0; risk 0.
2. Temperature schedule `ETHER_SAMPLE_TEMP=0,0.7` — sim +7.5–14 % kept per pool if duplicates are common; cost 0
   extra calls; risk low (gate unchanged), watch revert rate.
3. Reply dedup `ETHER_DEDUP_REPLY=1` — saves a gate run per duplicate; risk only of a missed keep on a flaky test.
4. Exemplar utility ranking — needs Phase-0 data.
5. LinUCB-9f / hierarchical TS — +0.3–0.5 kept in the sim's contextual scenario; only if by_via spreads.
6. Best-of-k with gate verification — larger possible gain, k× model and gate cost on a 1650; after 2.
7. Off-box KTO/DPO — needs ≥1–2k graded attempts and off-box GPU; not before.
Not recommended: discounted/sliding-window TS, goal-selection bandit, cost-aware TS as default, gem-rule bandit,
partial-credit reward.

## 8. Phased plan (after Phase 0)

- **Phase 0 (existing plan):** push batch 7 (+8 if accepted), run `ETHER_EXEMPLARS=record`, read
  `first_hour_report`: now also `duplicate replies` and `kept by temperature` (all T=0.0).
- **Phase 1:** if dup_share ≥0.15: `ETHER_SAMPLE_TEMP=0,0.7` (+ `ETHER_DEDUP_REPLY=1`) for one pool; compare
  retry-attempt pass rate, revert_rate, regressions_caught vs Phase 0. Stop rule: revert_rate or
  regressions_caught up at P≥0.9 → unset the flag.
- **Phase 2:** `ETHER_EXEMPLARS=1` arm A/B (exemplar utility), keeping the Phase-1 decoding decision.
- **Phase 3:** only if by_via spread ≥0.10: LinUCB-9f/hier TS for one pool on kept/GPU-h.
- **Phase 4:** best-of-k (k=2) with gate verification if the GPU budget allows; trajectories accumulated for
  an off-box KTO study (no host training).

## 9. Simulation method (`scripts/rl_sim.py`, results `docs/results/batch8/rl_sim.{json,md}`)

SIMULATION, 400 seeds, ~107 s on 6 procs. 60 real seed goals with real via/span/target/tractability;
MAX_TRIES 3, MAX_TARGET_TRIES 6, siblings on a target resolved together on a keep. Goal logit
z = A + B·(tract−0.25)/0.2 + N(0, σ) plus a share of unfixable goals. Scenarios (A, B, σ, unfixable sbfl,
unfixable other, DUP): low (−2.8, .5, 1, .45, .25, .8); mid, contextual (−1.8, .5, 1, .35, .15, .8);
low_dup03 / mid_dup03 (DUP .3); drift switches arm effects at attempt 60. Arm effects: minimal −0.1,
no_context −0.9, repo_map_on +0.2 (contextual: per-via/span effects). At T=0, re-pulling the same arm on the
same goal returns the earlier reply with probability DUP; temperature penalty −0.2 logit per 1.0 T; retry
penalty −0.5; gate 8 s, model 30 s. **DUP and the temperature penalty are assumptions** — Phase 0 measures the
first. Full tables (E1–E4): `docs/results/batch8/rl_sim.md`.

## Sources (each returned HTTP 200 on 2026-11-22)

- Russo et al., A Tutorial on Thompson Sampling — https://arxiv.org/abs/1707.02038
- Li et al., LinUCB — https://arxiv.org/abs/1003.0146 ; offline evaluation — https://arxiv.org/abs/1003.5956
- Agrawal & Goyal, TS for contextual bandits with linear payoffs — https://arxiv.org/abs/1209.3352
- Raj & Kalyani, Taming non-stationary bandits (dTS) — https://arxiv.org/abs/1707.09727
- Garivier & Moulines, D-UCB / SW-UCB — https://arxiv.org/abs/0805.3415
- Xia et al., TS for budgeted MAB — https://arxiv.org/abs/1505.00146
- Chen et al., Combinatorial MAB (ICML 2013) — https://proceedings.mlr.press/v28/chen13a.html
- Ng, Harada & Russell, reward shaping (1999) — https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf
- Bradley-Terry model — https://en.wikipedia.org/wiki/Bradley%E2%80%93Terry_model
- Rafailov et al., DPO — https://arxiv.org/abs/2305.18290 ; Hong et al., ORPO — https://arxiv.org/abs/2403.07691 ; Ethayarajh et al., KTO — https://arxiv.org/abs/2402.01306
- Brown et al., Large Language Monkeys (repeated sampling) — https://arxiv.org/abs/2407.21787
- Chen et al., Codex / pass@k — https://arxiv.org/abs/2107.03374 ; Wang et al., self-consistency — https://arxiv.org/abs/2203.11171
- Shi et al., prompt optimization as best-arm identification — https://arxiv.org/abs/2402.09723
- Graves et al., automated curriculum learning — https://arxiv.org/abs/1704.03003
- Pan et al., SWE-Gym — https://arxiv.org/abs/2412.21139 ; Jimenez et al., SWE-bench — https://arxiv.org/abs/2310.06770
- Dettmers et al., QLoRA — https://arxiv.org/abs/2305.14314 ; Unsloth — https://github.com/unslothai/unsloth
