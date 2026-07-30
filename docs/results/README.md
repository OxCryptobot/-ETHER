# docs/results — raw-data provenance policy

Audit anchor: **MEAS-004** (published ablation rows lacked raw-data
provenance). This directory exists so that every number published in
`docs/FINDINGS.md` / `STATUS.md` can be traced to the rows that produced it.

## Files

- `ablation_qwen2.5-3b.json` — **raw rows** of run `20260729_020631`
  (qwen2.5:3b, headroom_v1, 40 tasks × 3 arms × 3 seeds = 360 samples,
  including the per-task table). This is the *contaminated* run: retrieval
  served solutions into prompts (leak channel 7, see `docs/FINDINGS.md` §2),
  producing the retracted `ether 0.875`. It is kept deliberately — a retracted
  number stays on the record with its rows, it is not deleted.
- `ablation_qwen2.5-3b_clean.json` — the rows behind the **published** numbers
  (`bare 0.317 / bare+sys 0.333 / ether 0.292`, ether − bare+sys = −0.042,
  McNemar p = 0.22). It is *not* a row-filter of the file above: it is re-run
  `20260729_050335` of the same model/dataset/decode with the leak guards on
  (`leak_guards: "assertions + solution-identity"`), and its `supersedes`
  field names the run it replaces.

## Selection criteria (what "clean" means, per `scripts/ablation.py`)

The harness enforces these rules on itself; a results file is publishable only
if produced under all of them:

1. **One grader for every sample** — `core.holdout.grade_against_holdout`,
   including re-grading the `ether` arm; never an exit-code proxy.
2. **Leak guard before send** — every prompt passes `core.prompt_guard.check`;
   a leaked sample is excluded from the denominator and counted separately,
   never scored a pass. (Its absence is exactly what voided run `020631`.)
3. **Fixed seeds, explicit decode** — every sampling parameter is recorded
   next to the model name, model digest, git commit and dataset id; a run with
   unknown decode proves nothing.
4. **Errors count as fails**, and the run aborts early if the error rate
   exceeds 25% after 15 samples, so a number never measures infrastructure
   failure instead of code quality.
5. Statistics support the claim: bootstrap CI clustered on tasks, exact
   McNemar on paired per-task outcomes, and a stated minimum detectable effect.

## Reproduction

```
python scripts/ablation.py --dry-run   # validate + plan (no GPU calls)
python scripts/ablation.py --resume    # the full run / resume after a crash
```

Requires a local model server (ollama) with the named model; see the module
docstring of `scripts/ablation.py` for the full contract.

## Policy going forward

Published numbers **MUST** ship their raw rows alongside (this directory, or
the append-only `memory/bench/ablation_samples.jsonl` referenced from the
results file). A published aggregate without inspectable per-task rows is a
MEAS-004 regression.
