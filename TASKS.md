# @ETHER Task Board

**Updated:** 2026-07-29 — post-audit. See `docs/FINDINGS.md` and `docs/COWORK.md`.

## Shipped (2026-07-27 → 29)

- Honest verification: `core/assert_audit.py`, `core/holdout.py` (mutation score 0.966)
- `core/prompt_guard.py` — leak detection by inspecting the finished prompt
- **7 leak channels closed**, including retrieval serving prior *solutions*
- Sandbox fails closed + hardened (`uid 65534`, `--read-only`, all caps dropped)
- Decode control — the model had been running at `presence_penalty=1.5`
- `scripts/ablation.py` — the first `ETHER − bare model` measurement
- Mutation-scored suites: `build_headroom.py`, `build_calibrated.py`
- Guardian per-mode baselines, ratchets up only
- Bandit redesign: 10 arms → 6 real mechanisms, per-context stats
- `core/agent_loop.py` + `core/verifier.py` — built, wired, measured
- Tests 48 → **763**; `pytest` no longer mutates production state

## Corrections to the old board

These were listed as shipped and were **not true**:

- ~~"decide_burst reads curriculum tier automatically"~~ — `tier=0` was
  hardcoded at the call site, so the tier rule was unreachable.
- ~~"verification_score through flywheel gates"~~ — it measured "the process
  exited 0". A no-op function scored 1.000.
- ~~"Curriculum-only objectives + assert nudge"~~ — the objectives contained
  their own answers, and the nudge contradicts 21 of 40 task specs.

## Next — ranked by evidence, not appeal

1. **Repo-grounded benchmark.** Revert real commits, ask the agent to restore
   behaviour, judge by the repo's own test suite. This is the only setting
   measured to have real headroom, and its oracle cannot be leaked.
2. **Tool layer + outer loop** — `read`, `edit`, `search`, `run_tests`, with
   exact-match edits that fail loudly and rollback on a bad trajectory. The
   orchestrator is currently decorative: 8 states, 2 unreachable, nothing reads
   its verdict.
3. **Static analysis in the verification loop** — ruff/mypy work on tasks with
   *no* holdout, which is every real task.
4. **Flywheel as a data engine, not an online learner.** The bandit has ~54
   pulls and needs ~1,000. Accumulate verified solutions and fine-tune on them.

## Do not do

- **Optimise the best-of-N selector.** Ceiling measured at 5.8pp.
- **Add prompt scaffolding to improve single-file generation.** Measured
  neutral-to-negative on both a 35B and a 3B.
- **Trust any pre-2026-07-29 score.**
