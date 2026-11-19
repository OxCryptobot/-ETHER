# Neuroevolution for ETHER self-improvement — evaluation (2026-11-19, branch ether-batch1)

Doctrine held: single writer, honest gate (test-pass reward only), GTX 1650 4GB / 4B Q4 model,
no gradient RL through the model, Matrix read-only, tool-first. Fitness = honest-gate outcome.

## What can be evolved, and what each costs on the 1650

| Target | Method fit | Fitness eval | Cost on 1650/4B |
|---|---|---|---|
| Bandit arm priors / exploration (7 arms x 3 buckets = 21 params) | (1+lambda)-ES, CMA-ES, OpenAI-ES | **offline** IPS replay of stored trajectories | CPU 8-36 ms per fit, 0 VRAM (measured, `scripts/es_replay_bench.py`) |
| Gem decision policy (`core/agent/gems.py:chain`) | ES over thresholds / tiny NEAT net | offline replay only if decisions + outcomes are logged (not yet) | CPU only; data-starved today |
| Tool sequences (search/read/edit/test order in `react.py`) | GA / MAP-Elites (niches = tool count x goal kind) | **live** honest gate per candidate | one live 4B job p50 136 s, p95 325 s (`artifacts/latency_slo.json`, n=271, measured 2026-09-12) => ~12-26 evals/hour |
| Prompt text / adapters (EvoPrompt, Promptbreeder) | LLM-as-mutation GA/DE | **live** honest gate x dev set | pop 10 x 10 gens x 10 tasks = 1000 evals ~ 38-90 GPU-hours at the latency above; 4B is a weak mutation operator |
| Network topology (NEAT, HyperNEAT) | evolves a policy net from features | needs a feature vector per decision + replay | CPU-trivial net, but no benefit over a 21-logit table at this data size; HyperNEAT targets large geometric nets — no fit here |

Model weights are out of scope: a 4B Q4 at 2.7 GB of 4 GB VRAM (`artifacts/gpu_metrics.json`) leaves no room for
population-based weight perturbation, and doctrine forbids gradient RL through the model.

## Prototype (flag off)

- `core/agent/evolve_es.py` — (1+lambda)-ES, 1/5th success rule. Genome = one logit per (bucket, arm) of the
  existing `core.learning.BanditPolicy`, seeded from the bandit's own scores. Fitness = SNIPS honest-gate pass
  rate minus 1 standard error at the policy's effective sample size, anchored L2 to the bandit seed. Fit on 70%
  of trajectories, gate on the held-out 30%.
- `core/agent/outcome.py:choose` — with `ETHER_SOTA_EXPLORE=1` and `ETHER_NEURO_ES=1`, an *accepted* candidate
  replaces only the epsilon-greedy exploration draw (propensity logged). It never promotes; promotion stays in
  `outcome.maybe_promote` (3 honest-gate passes, last attempt passed, score above incumbent).

## Measured: ES vs the existing bandit (offline replay, 30 seeds, SYNTHETIC pass probabilities)

True pass rate of the deployed exploration policy (known ground truth, Beta(1,3) arm pass rates, 7 arms x 3 buckets):

| logged attempts | bandit eps-greedy | bandit greedy | ES | oracle | holdout gate accepted | gate precision | deployed w/ gate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | 0.4235 | 0.4407 | 0.4395 | 0.5655 | 1/30 | 1.00 | 0.4241 |
| 300 | 0.4886 | 0.4972 | 0.4842 | 0.5655 | 7/30 | 0.43 | 0.4838 |
| 1000 | 0.5090 | 0.5152 | 0.4923 | 0.5655 | 8/30 | 0.38 | 0.5064 |

Earlier variants were worse (plain SNIPS fitness gated on fit data: ES 0.33, gate accepted 12/30 with 0% precision;
absolute L2 pulled policies to uniform). Real replay data: only 10 non-scripted scoreboard rows exist in the repo
(1 pass), with no logged propensities — too small to conclude anything.

**Verdict: do not turn ES on.** For a 21-parameter discrete choice the existing bandit is already near the
best achievable from the same data, and the holdout gate is not precise enough (<50% at 300+ attempts) to trust
an ES candidate. Keep the bandit + honest-gate reward (commit 2) as the learning path.

## Where evolution could pay off later (measured next steps)

1. Log gem decisions and react tool sequences into `memory/learning/trajectories.jsonl` (cheap; enables replay).
2. MAP-Elites (pyribs) over tool-sequence programs evaluated by the *scripted* honest gate (pytest only, no LLM,
   ~2 s p50 per `latency_slo.json` scripted) — feasible on CPU; promote a program only after live honest passes x3.
3. EvoPrompt-style prompt evolution only off-box (>=12 GB VRAM or a keyed outsource model as mutation operator),
   with the 4B evaluated by the honest gate. Budget it in GPU-hours before starting.
4. Re-run `scripts/es_replay_bench.py` on real trajectories once >=300 graded attempts with logged propensities exist.

## References (verified 2026-11-19)

- NEAT: Stanley & Miikkulainen 2002, https://doi.org/10.1162/106365602320169811 ; neat-python https://github.com/CodeReclaimers/neat-python
- HyperNEAT: Stanley, D'Ambrosio, Gauci 2009, https://doi.org/10.1162/artl.2009.15.2.15202
- OpenAI-ES: Salimans et al. 2017, https://arxiv.org/abs/1703.03864
- CMA-ES: pycma https://github.com/CMA-ES/pycma
- JAX ES library: evosax https://github.com/RobertTLange/evosax
- MAP-Elites: Mouret & Clune 2015, https://arxiv.org/abs/1504.04909 ; pyribs https://github.com/icaros-usc/pyribs
- EvoPrompt (ICLR 2024): https://github.com/beeevita/EvoPrompt
- Promptbreeder (ICML 2024): https://arxiv.org/abs/2309.16797
