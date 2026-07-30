# ADR 0002: Day-1 Security Fail-Closed (ETHER roadmap, day 1 of 5)

## Status

Accepted — Day 1 of 5 of the security hardening roadmap. Closes findings
B1/S-01 (sandbox auto→local fallback invisible) and B2/S-03 (push-to-exec
command channel via the tracked batch queue).

## Context

- **B1/S-01 (invisible host execution):** probe-verified that with the
  backend on `auto` and no docker binary, `ClearQuartz.execute()` ran
  model-authored code host-side — with the host filesystem, network and
  PATH — while the response carried `security_flags=[]`, indistinguishable
  from container isolation. The `sandbox_fallback:local` marker existed
  only on the `FileNotFoundError` degrade path, but both local paths
  (explicit-`local` and auto-resolved-`local`) reach `_run_local` via
  `_run` without ever raising it. `deploy/ether.service:10` pinned
  `ETHER_SANDBOX_BACKEND=local` for the production daemon.
- **B2/S-03 (push-to-exec):** the tracked `memory/batch_queue.json`
  carried pending item `{"id": 34, "kind": "command", "command": ["python",
  "scripts/bench.py"]}`; `scripts/batch_worker.py:72-80` executes queue
  commands verbatim, and the flywheel's `batch_tick` drains the same
  queue — so a pushed JSON file was a remote command-execution channel on
  the daemon host.
- Audit anchors: SEC-003, SEC-004, SEC-008 of the continuous-audit pack.

## Decision

- **Visibility marker on every local success path.** `execute()` computes
  `backend = sandbox_backend()` once, before `self._run(...)`, and appends
  `sandbox_fallback:local` to the response `security_flags` whenever the
  resolved backend is `local`. The static-analysis score split is
  preserved (`static_analysis_score = 0.0 if security_flags else 1.0`,
  computed from static flags only, mirroring the deliberate split in the
  `FileNotFoundError` path), so the marker alone does not tank the score.
- **Command channel env-gated closed at BOTH enqueue and execution.**
  `core/batch_queue.enqueue` refuses `kind="command"` unless
  `ETHER_BATCH_COMMANDS=1`; `scripts/batch_worker.process_one` records an
  error instead of running command items unless the same opt-in is set
  (defense in depth: an item that predates the enqueue guard, or was
  pushed directly, dies recorded, not run).
- **Tracked queue purged.** Pending item id 34 removed from
  `memory/batch_queue.json`; the 3 pipeline smoke items are byte-stable.
- **Service file explicit docker.** `deploy/ether.service` now sets
  `ETHER_SANDBOX_BACKEND=docker` with the B1 rationale comment; `local`
  requires deliberate operator opt-in.

## Deliberately NOT changed

- `_run`, `_run_local`, `_run_docker`, `sandbox_backend`, and the
  `execute()` exception handlers: the auto `FileNotFoundError` flag path
  and the explicit-docker fail-closed behavior are already correct and
  are now pinned by `tests/test_day1_security.py`.
- The flywheel `batch_tick` default: the downstream refusal in
  `process_one` closes the channel wherever it is drained — defense in
  depth rather than a flag on every caller.
- `autonomy-host.yml`: the runner executing pushed repo code is the
  daemon's design, mitigated by the Day-2 report-commit stop and Day-3
  PR CI, not by this stage.

## Consequences

- Developers on dockerless machines now see `sandbox_fallback:local` on
  every sandbox run — that is the point: host-side execution is never
  again indistinguishable from container isolation.
- The audit pack's SEC-003/SEC-008 contract xfails flip to XPASS
  (behavioral contracts: auto-fallback emits the flag; the tracked queue
  carries no command items). SEC-004 (deploy pin) and SEC-008 (tracked
  command item) are resolved in the static register. The SEC-003 static
  heuristic still reports its single baselined violation at
  `sandbox.py:_run` (the direct `_run_local` dispatch), because the
  marker now lives in `execute()` — one frame up — which the rule's
  per-function scan cannot see; clearing it would require touching
  `_run`, which this ADR explicitly forbids. The behavioral contract is
  what gates (XPASS), and the gate stays clean (no NEW blockers).
- QUAL-005 budget note: the two new env gates (`ETHER_BATCH_COMMANDS` in
  `core/batch_queue.py` and `scripts/batch_worker.py`) raise the
  `env_getenv_sites` actual from 189 (stage-1 sanctioned) to 191 against
  the pack's budget of 188. Both sites are security opt-ins that must be
  read at the enforcement point; the budget should be raised to 191 by a
  human PR per the pack's ratchet policy.

## Rollback

- `ETHER_BATCH_COMMANDS=1` re-enables command queue items on a trusted
  machine (both enqueue and execution honor it).
- `ETHER_SANDBOX_BACKEND=local` re-selects host execution for the daemon;
  the run is still flagged, so the rollback is visible, not silent.

## Roadmap fit

Day 1 of 5. Next: Day 2 promote gate + signal rebase.
