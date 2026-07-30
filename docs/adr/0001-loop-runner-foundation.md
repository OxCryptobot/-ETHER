# ADR 0001: Loop-Runner Foundation (migration stage 1 of 6)

## Status

Accepted — stage 1 of 6 of the octagon migration (roadmap §7/§8).

## Context

- **A-1 (god method):** `Pipeline.run` was a 788-line method
  (`core/pipeline.py:161-948`) mixing planning, generation, sandbox, audit,
  critique, holdout, reward, and finalize in one untestable control flow.
  The audit pack's ARCH-003 budget (790 lines, AST end−start span) measured
  784 at HEAD — 6 lines of headroom, so any feature addition forced either a
  violation or an unmaintainable squeeze.
- **A-3 (silent seams):** six capability losses vanished into
  `except: pass` — citrine registration (`core/registry.py`), grandidierite
  tool discovery, the agent-loop fallback, experience recording (twice),
  auto-fabrication, and run persistence — so a degraded run was
  indistinguishable from a healthy one.
- **P-07 (state convergence):** memory/ state files were written by many
  modules with ad-hoc or missing locking; only `core/batch_queue.py:19-52`
  had the proven O_EXCL-lockfile + tmp-replace pattern.
- Audit anchors: A-1, A-3, A-4 (untyped edges), P-07, ARCH-001/003/004,
  STATE-001, QUAL-002 of the continuous-audit pack.

## Decision

- **Extraction boundary = the finalize tail.** The last ~112 lines of
  `Pipeline.run` (record outcome → experience → auto-fabricate → memory_save
  → status derivation, legacy `pipeline.py:827-938`) move into
  `core/loop/handlers/finalize.py::FinalizeHandler`, dispatched by the thin
  `core/loop/runner.py::LoopRunner`. The legacy inline block moves verbatim
  into `Pipeline._finalize_legacy` and stays the default.
- **Strangler flag `ETHER_LOOP_RUNNER`.** Default off. `=1` routes the tail
  through `LoopRunner.run_finalize`. The flag branch and the legacy path are
  proven byte-equivalent by `scripts/shadow_runner.py` (per-scenario diff of
  stages/status/error/degraded plus side-effect call logs; volatile keys
  `duration_ms`/`finished_at`/`task_id` excluded).
- **Typed edges committed now.** `core/vectors.py` lands the `Vector` /
  `Provenance` schema and `prompt_hash()`; `PipelineResult` gains
  `degraded: List[str]`. Nothing emits Vector on the default path yet — the
  envelope fields are committed so stage 2+ handlers adopt Vector without
  another schema migration.
- **Degradation is data.** Every silent seam listed above now appends an
  exact `name:{ExceptionType}` string to `result.degraded`; the registry
  records `citrine_unavailable:{ExceptionType}` and `Pipeline` seeds every
  run's degraded list from it.
- **Spine kernel + batch_queue equivalence.** `core/spine/state_io.py`
  generalizes the batch_queue lock/atomic pattern (`state_lock`, `read_json`,
  `write_json`, `rmw`, `append_jsonl`); `core/batch_queue.py` is
  re-implemented on it with zero API/behavior change (guarded by its
  unmodified existing tests), and `Pipeline._persist` writes via
  `write_json` (atomic).
- **Topology guards.** `tests/test_topology.py` enforces D1 (gems→core
  only leaf contracts), D2 (core→gems inversion; hard zero for `core/loop`,
  `core/spine`, `core/vectors.py` except the single sanctioned lazy bridge in
  `LoopRunner._default_run_tool`), D3 (single state writer), D4 (dashboard
  reads via collector), D5 (entry points don't import the god object) with
  embedded, shrink-only grandfather allowlists generated at 208993a.

## Consequences

- `Pipeline.run` shrinks from 784 to 702 (AST end−start span; the 112-line
  tail replaced by a 26-line dispatcher branch) — ARCH-003 headroom grows
  from 6 to 88 lines.
- Degraded runs are observable on every `PipelineResult` and in every
  persisted run record; gates can finally see capability loss.
- Topology drift (new layering inversions, new state writers, new dashboard
  reads) is CI-failing instead of review-by-eye.
- `core/loop`, `core/spine`, `core/vectors.py` carry zero `gems.*` imports
  (one sanctioned lazy bridge), so the extraction path is independently
  testable and importable.
- One new `ETHER_*` getenv site (`ETHER_LOOP_RUNNER`) — the flag itself.

## Roadmap fit

This stage is the Day-4 kernel (state_io, vectors) plus the Day-5 stage-1
extraction (finalize tail + flag + shadow proof). Next: stages 2–6 per
roadmap §7 (remaining handler extractions behind the same flag), the
state-writer migration for experience / failure_graph / curriculum /
fail_streak onto `state_io`, then flag default-on and deletion of
`_finalize_legacy`.

## CI integration notes

- **Matrix job:** run the pytest step with `ETHER_LOOP_RUNNER ∈ {0, 1}`.
  Both legs must produce identical results — the suite pins behavior either
  way.
- **Shadow gate:** `python scripts/shadow_runner.py --selftest` as a CI step
  (exit-gated; `--max-scenarios N` for smoke). A red shadow run means the
  extracted path drifted from legacy — block the merge.
- **Topology in the default suite:** `tests/test_topology.py` runs with
  `pytest tests/`; new D1–D5 violations fail locally before CI.
- **How this unblocks commits:** every future extraction PR is provable by
  shadow + matrix instead of review-by-eye — the differ compares observable
  behavior, so "no behavior change" becomes a checked artifact rather than a
  claim. That is what makes continuous builds trustworthy again.
- **Audit-pack interaction:** ARCH-003 is a line-count ratchet (headroom
  3 → 88 this stage); STATE-001's writer count stays flat as state writers
  migrate onto the Spine kernel (count drops as stages 2+ land); the D-rules
  in `tests/test_topology.py` mirror the pack's ARCH/STATE rules with
  embedded site allowlists, so a violation fails locally before the pack
  ever runs in CI.
