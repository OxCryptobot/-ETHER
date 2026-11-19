# Automated refactoring for ETHER (batch 2, 2026-11-19)

Scope: refactors the single writer (`scripts/host_main.py` under ETHER-Host) may
keep on the 1650 (GTX 1650 4 GB, qwen3.5:4b). Doctrine: honest gate only (a tool
edit that keeps every previously passing test green), surgical patches, Matrix
read-only, no generate-fallback counted as PASS, no new dependency on the host.

## What shipped (flag `ETHER_REFACTOR=1`, default off)

`core/agent/refactor.py` adds a `refactor` goal kind to the same queue
(`core/agent/sota.next_goal`: real failing-test/lint goals first, then refactors,
then the retired legacy ladder only with `ETHER_SOTA_LEGACY=1`).

| strategy | candidate rule | edit |
|---|---|---|
| `remove_filler` | top-level zero-arg `describe/add_name/failing_test/fits_name/clamp_name/ready` returning a constant, or the `count_defs()` template; no import/attr/getattr reference elsewhere | delete the function (stdlib `ast` line span) |
| `dead_code` | private top-level `_name` (no decorator) whose identifier occurs exactly once in core/scripts/gems/tests/cli/tools/dashboard | delete the function |
| `ruff_safe` | file with a fixable `F401` (not in `__init__.py`), `F541`, `UP034` | `ruff check FILE --select ... --fix` (safe fixes only); skipped when ruff is absent |

Gate per candidate: guard suite = the module's importing test files (up to 6,
smallest first) + smoke files; `ETHER_GUARD_SUITE=full` runs all of `tests/`.
Run it before the edit, apply, compile, run it again; keep only if no test that
passed before fails after and at least one test covered the file. Otherwise the
file is restored byte-for-byte. Results are tool edits (`policy: "tool"`), never
credited as model capability.

Bandit: one arm per strategy in `memory/learning/refactor_arms.json`, picked by
optimistic mean `(kept+1)/(pulls+2)` (untried first, then the best keeper).
This is a small separate table, not `core.learning.BanditPolicy`, because that
class's arm set is the prompt-strategy list.

## Measured on the repo (Linux CPU, scratch copy of this branch, mock-free)

`out/refactor_replay.py` ran every candidate through `refactor.attempt()`:

| strategy | candidates | kept by gate | regression caught + reverted |
|---|---|---|---|
| remove_filler | 56 | 56 (100%) | 0 |
| dead_code | 1 | 1 | 0 |
| ruff_safe | 40 | 39 (97.5%) | 1 (`core/pipeline.py`: `tests/test_stage_mark.py::test_pipeline_uses_skip_detail` reads the source) |
| total | 97 | 96 (99.0%), 193 lines removed | 1 |

Wall time 427.7 s for 97 candidates (about 4.4 s each, two guard runs per
candidate) on the box CPU.

Did the subset guard miss anything? The 40 kept `ruff_safe` + `dead_code` edits
were applied together to a fresh copy and the full suite was run: 0 tests that
passed on the branch failed (1610 pass / 75 fail / 85 skip vs the branch run).
The reviewed cleanup commit ("batch2 cleanup") was also checked with the full
suite on the real tree. It removed four ladder stubs by hand that the tool
skips (`add_name`, `failing_test`, `fits_name`, `clamp_name` are named in
`core/agent/learn.py` strings, so the reference check refuses them). Removing
`fits_name` exposed a vacuous test
(`tests/test_agent_runtime.py::test_the_runtime_edits_a_real_file` matched
`def fits` against `def fits_name`); it is now xfail with the reason.

Candidate counts on the tree at the time (ruff 0.17.6, vulture 2.16 for
comparison only): ruff F401/F541/UP034/F841/F811/E711/E712 = 110 findings;
vulture at 100% confidence = 7, at 60% = 179 "unused function" (most are entry
points, test hooks or dynamic dispatch, which is why the shipped rule only
deletes private names with a single occurrence); F821 undefined names = 17
(3 in core: `core/eligible_rates.py`, `core/kernel/product_loop.py`,
`core/kernel/repo_fail.py`), which are bugs, so they are lint *goals* for the
model (`core/agent/goal_source.lint_goals`), not refactors.

## Options evaluated

(a) Rule-based / AST. Shipped: filler, private dead code, ruff safe fixes.
Not shipped yet: rename with call-site update (rope `rename` does this with a
project-wide occurrence finder; needs rope on the host), extract method
(rope `extract`), simplify conditionals (ruff `SIM` rules are partly unsafe
fixes; would need `--unsafe-fixes` and the gate). libcst would give
comment-preserving transforms; stdlib `ast` line spans are enough for deletes.

(b) LLM-guided refactor. A 4B proposes a small diff, the same gate verifies.
The literature says to filter hard before trusting it: Pomian et al. found up
to 76.3% of LLM extract-method suggestions were hallucinations and only static
analysis filtering + IDE application made them safe (EM-Assist, 53.4% top-5
recall on 1,752 real refactorings). Cordeiro et al. (StarCoder2-15B, 5,194
refactoring commits) gated by unit tests and found pass@5 28.8% above pass@1.
For ETHER that maps to: model proposes *which* function to extract/rename,
the tool performs it, the gate decides; behaviour preservation = the guard
suite, plus an optional differential check (call the old and new function on
the test inputs and compare). Not shipped: no host measurement yet, and a 4B
on the 1650 costs ~20-70 s per call (supervisor pass times 18.7-71.9 s today).

(c) Evolutionary search over refactor sequences. Not worth it now: 96 of 97
single deterministic refactors already pass the gate, so the search space has
almost no failures to optimise around; each fitness evaluation costs two guard
runs (~4.4 s CPU). Revisit when LLM-proposed refactors exist.

## Next measured steps

1. On the 1650 set `ETHER_REFACTOR=1` for one day; expect the remaining
   `ruff_safe`/`dead_code` candidates to drain at <=2 per tick; check
   `memory/learning/refactor_arms.json` and that no kept refactor shows up as a
   regression in the next full run.
2. Add `ETHER_GUARD_SUITE=full` for refactors only when the host is idle (full
   suite on Windows has not been timed; Linux is 285 s).
3. Prototype rope rename/extract behind the same gate on the box first.

## Sources (opened 2026-11-19)

- LibCST: https://github.com/Instagram/LibCST
- rope: https://github.com/python-rope/rope
- vulture: https://github.com/jendrikseipp/vulture
- Ruff linter, fix safety ("Ruff only applies safe fixes by default"): https://docs.astral.sh/ruff/linter/
- Pomian et al., "Together We Go Further: LLMs and IDE Static Analysis for Extract Method Refactoring", arXiv:2401.15298
- Pomian et al., "EM-Assist: Safe Automated ExtractMethod Refactoring with LLMs", arXiv:2405.20551
- Cordeiro, Noei, Zou, "An Empirical Study on the Code Refactoring Capability of Large Language Models", arXiv:2411.02320
