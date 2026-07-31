# ADR 0005: Stage-2 Verification-Spine Extraction (migration stage 2 of 6)

## Status

Accepted — stage 2 of 6 of the octagon migration (roadmap §7/§8; stage 1 =
ADR 0001, finalize tail, merged).

## Context

- **A-1 (god method):** after stage 1, `Pipeline.run` still spanned 718 lines
  (AST end−start, ARCH-003 budget 718 — zero headroom). The largest coherent
  unextracted segment was the **verification spine**, legacy
  `core/pipeline.py:649-841`: everything after the generation while-loop's
  `last_err/fail_kind` lines and before `_credit_attempts` — tool_scan,
  audit, critique, gate inputs, prompt_guard + holdout grading, and the
  learning reward.
- The spine is the architecture's *named* segment: it is the sequence that
  turns a generated artifact into a verified verdict (scan → audit → critique
  → leak guard → unseen-assert grading → reward). Extracting it as one unit
  keeps the trust boundary — "everything that decides how much we believe the
  artifact" — in one testable handler.
- **Why not the generation loop next:** the decomposition proceeds
  tail-first in entanglement order. The generation while-loop is entangled
  with the agent-loop control-flow exception (`_LoopAlreadyGenerated`), the
  burst env-var dance, retry re-draws and lazy retrieval closures; the spine
  only *reads* run state and writes `result` fields, so it extracts cleanly
  today, and removing it shrinks the loop's surroundings first.

## Decision

- **Extraction boundary = the verification spine.** Legacy
  `pipeline.py:649-841` moves VERBATIM into
  `Pipeline._verify_legacy(self, result, *, objective, generated, critique,
  holdout_test, sent_prompts, tool_assist)`, returning
  `Tuple[Optional[int], int, str]` = `(exit_code, total_tests, effective
  holdout_test)`; everything else still mutates `result` exactly as the
  inline block did. The default (flag-off) path is byte-identical by
  construction.
- **Flag path mirrors stage 1 exactly.** `ETHER_LOOP_RUNNER=1` routes the
  spine through `LoopRunner.run_verify` →
  `core/loop/handlers/verify.py::VerificationHandler`, with a pydantic v2
  `extra="forbid"` `VerificationContext`/`VerificationOutcome` pair,
  constructor-injected `registry`/`run_tool`, zero `gems.*` imports under
  `core/loop` (D2 hard zero), and StageResult-shaped DICTS out (never an
  import of `core.pipeline`). The dispatcher in `run()` applies the outcome
  (stages/confidence/audit/critique/holdout_ok/reward) and unpacks the
  returned gate triple, so the downstream finalize dispatch consumes the
  RETURNED `exit_code`/`total_tests`/`holdout_test` in both branches.
- **The `holdout_test` mutation channel is preserved as data.** On a prompt
  leak the legacy block reassigns the local `holdout_test = ""` to skip
  grading; the handler returns the effective value in the outcome and the
  dispatcher rebinds the local, so the finalize tail (experience record,
  memory-save holdout tagging) sees the post-mutation value on both paths.
- **Reward-before-credit ordering is unchanged.** `compute_reward(...)` is
  the last spine step; `self._credit_attempts(attempts, result)` stays in
  `run()` AFTER outcome application because it needs the bandit `attempts`
  local and a set `result.reward`.
- **Fidelity invariants pinned by the shadow harness:** stage names/details
  (`tool_scan`, `audit`, `critique`, `prompt_guard`, `holdout`), confidence
  clamps (0.25 on not-clean/risky tool_scan; 0.3 on audit reject AND on
  audit outage), audit-outage neutral-True for `compute_reward`
  (`audit_approved=True` when no verdict exists, while the clamped
  confidence keeps the reward deflated), guard fail-closed leak handling,
  holdout grading fail-closed on exception, guard fail-open on exception,
  `compute_reward` kwargs byte-identical, `write_progress` calls
  ("tool_scan", "audit"), and the `if tool_assist and generated` /
  `if critique` guards.
- **Budget ratchet (ARCH-003).** `Pipeline.run` now measures **572** lines
  by the rule's own metric (end_lineno − lineno; 718 → 572). The budget is
  set to the measured value (may-only-lower) in both
  `config/audit-rules.yaml` and `tools/audit/findings_baseline.json`. No
  baseline reseed was needed: the ARCH-003 entry stays FIXED and the actual
  only shrank, and shrink-below-budget never fires (ratchet semantics);
  documented in the baseline notes.
- **Topology.** `core/modules.yaml` registers `loop/handlers/verify`
  (ARCH-005). The D2 allowlist in `tests/test_topology.py` is re-pinned with
  why-comments: three sites +1 (the `VerificationContext` import line), the
  tool_scan `run_tool` import travelled verbatim into `_verify_legacy`
  (:653 → :771), and the two post-`run()` sites shifted with the insertion
  (:966 → :1034, :1034 → :1102). Same file, same module, no new sites.

## Consequences

- `Pipeline.run`: 718 → 572 lines (ARCH-003 headroom 0 → 0 at the new,
  lowered budget; the budget tracks the measured reality).
- The spine is unit-testable without gems: `tests/test_loop_verify.py`
  exercises every branch with a stub registry/run_tool, plus flag-routing
  and end-to-end flag-parity tests.
- `scripts/shadow_runner.py` proves byte-equivalence scenario by scenario:
  9 finalize + 17 verify scenarios (audit approved/rejected/outage,
  audit payload type mismatch, critique on/outage, critique payload type
  mismatch, tool_scan risky/dirty/raises, tool_scan dirty + audit rejected
  clamp precedence, holdout pass/fail/leak,
  guard raise fail-open, grade raise fail-closed, no-sandbox), diffing
  stages (minus `duration_ms`), confidence, audit/critique payloads,
  holdout_ok, effective holdout_test, reward, exit_code, total_tests, and
  every boundary call log. The perturbation probe (single-string drift in a
  stage detail) fails the selftest with a nonzero exit.
- One deviation from the stage-2 SPEC pseudocode: `LoopRunner` constructs
  `VerificationHandler` in `__init__` (constructor-injected `run_tool`),
  mirroring how `FinalizeHandler` is actually wired in `runner.py`, rather
  than the SPEC's `self.registry`/`self._run_tool()` sketch — the SPEC's own
  fallback instruction ("read how run_finalize injects and mirror it
  exactly") governs. The measured `Pipeline.run` span is 572 lines against
  the SPEC §7 estimate of ~520-560; the SPEC mandated recording the
  measured value, so this is compliant. `tests/test_loop_runner.py`'s
  `FakeRunner` also gained a `run_verify` pass-through stub so the existing
  runner tests remain valid under the flag-on dispatch.

## Residuals / next seams

`run()` is still ~572 lines: plan+extend, the retrieval blocks, and the
generation while-loop (with the agent-loop control-flow seam and burst
env-var dance) remain inline — stages 3–5 of the 6-stage plan, in
entanglement order, before flag default-on and deletion of
`_verify_legacy`/`_finalize_legacy` at stage 6.

## CI integration notes

- Same as ADR 0001: the pytest matrix runs `ETHER_LOOP_RUNNER ∈ {0, 1}`;
  both legs pin behavior. The shadow selftest (now finalize + verify
  scenarios) stays an exit-gated CI step; a red shadow run blocks the merge.
- ARCH-003's budget now equals the measured span (572); any growth of
  `Pipeline.run` fails the gate, and further extractions ratchet the budget
  down with the measured value.
