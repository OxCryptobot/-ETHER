# Batch 10: idle-host fix, OS jail, MCP, LSP, attic, swarm (2026-11-26)

Branch `ether-batch10` on top of `ether-batch9-gaps` (batch 9 is live: origin `main` contains merge
`c7c0d44414`; checked against `3eb62be522`). Nothing was pushed. Every item has its own commit and tests
(`tests/test_batch10_*.py`). Full-suite comparison vs the batch 9 baseline (2011 tests / 1857 pass / 71 fail /
83 skip): see "Test results" at the end.

## 0. Why the host stopped learning, and the fix — done (no flag needed)

**Live evidence (origin main `3eb62be522`, artifacts written by the 1650, read 2026-11-26 ~12:45 Bogota):**
- `supervisor.json`: cycle 92, pull ok, pull_failures 0, `health_worst` = "queue: goal queue empty", `dry_streak` 92.
- `host_main.json`: `next_goal` "none", `sota.note` "queue empty", but `real_queue` = open 95 / done 3 / dropped 28;
  `sota.scan` = 8 files in 54.7 s (6.8 s per test file on the 1650).
- `sota.json` `last.ts` = 2026-11-24T21:14Z: no attempt since (the `sota_stale` signal: 160,396 s).
- `learning_summary.json` `recent`: 18 of the last 25 attempts are `gate aborted: baseline timeout` with
  `secs` 181.8–192.8, i.e. the fixed 180 s `ETHER_GATE_TIMEOUT_S` plus setup. The same goal was aborted three
  times in 9 minutes (`fix_test_pipeline_code_stage_failure`, 07:26 / 07:30 / 07:35Z on 11-24) and then never
  tried again. Each abort was graded as a model failure (reward -0.9) although no model call was made.

**Mechanism (code):**
1. Batch 9 widened the guard suite (transitive importers + smoke + samples, ~15–18 files) and moved it into a
   synced sandbox. At 6.8 s per file the baseline needs ~110–190 s plus sync: over the fixed 180 s on many goals.
2. `sota._attempt_real` called `gs.mark(goal, kept=False)` on a baseline abort: one try spent, no model call.
3. `next_real` skips goals with `tries >= MAX_TRIES (3)` or an SBFL cluster with `>= MAX_TARGET_TRIES (6)`, and
   tries never expire. Once every open goal crossed one of those lines, `next_real` returned None forever.
4. `real_queue.open` comes from `ranked()`, which does not apply the try limits, so the host reported 95 open
   goals and "goal queue empty" at the same time. `goal_index.json` (where the tries live) is not published,
   so the exhaustion was invisible from origin.

**Fix (`core/agent/goal_source.py`, `core/agent/sota.py`, `core/agent/outcome.py`, `scripts/host_main.py`,
`scripts/host_signals.py`):**
- A baseline that cannot run goes to `mark_abort`: no try is spent, the goal backs off
  (`ETHER_ABORT_BACKOFF_S` 1800 s x 2^(n-1), max 24 h) and is parked only after `ETHER_ABORT_MAX` (6) aborts.
  `outcome.classify` treats it as `no_attempt`: no bandit update, not counted as a graded attempt.
- The timeout follows measurement: `artifacts/gate_timing.json` keeps an EWMA of seconds per test file from every
  completed guard run (a timeout only raises it). Timeout = max(180, 2 x secs/file x files) x 1.5 per earlier
  abort of that goal, capped at 900 s. With the host's own 6.8 s/file a 16-file guard gets ~219 s; after one
  timeout the estimate jumps to >= 1.25 x the observed time.
- Per-goal guard trimming after an abort: the target's test file and its direct importers always stay (the
  batch 8 guard); the transitive / smoke / sampled extras are halved per abort. The gate's after-run uses the
  same suite and timeout as its baseline, so the comparison stays like-for-like.
- Exhausted goals come back: after `ETHER_GOAL_RETRY_S` (48 h) x 2^round, up to `ETHER_GOAL_MAX_ROUNDS` (2)
  extra rounds, including SBFL clusters. Tries recorded before batch 10 carry no timestamp (many are the
  aborts above), so they are re-admitted once at the first run: the 95 open goals become selectable again.
- Health tells the truth: `host_main.real_queue` and `learning_summary.real_queue` gain `selectable`,
  `blocked` (by reason: exhausted, target_exhausted, abort_backoff, abort_parked, multi_off, missing_file),
  `next_retry`, `abort_reasons`, `secs_per_file`, `gate_timeout_s`. The queue signal reads
  "95 open real goals, 0 selectable; skipped: exhausted 60, ...; next retry ...; top abort: baseline timeout x5"
  and says "empty" only when `real_queue.open` is 0. On pre-batch-10 code it names the likely cause.
- Tests: `tests/test_batch10_queue.py` (10) replays the host's sequence (three baseline timeouts in a row:
  0 tries spent, no model call, trimmed suite, longer timeout, backoff, then selectable), legacy re-admission,
  cluster re-admission, retry-off = batch 9, timeout scaling and recording, trimming, the health text.
  `tests/test_batch3.py::test_sbfl_target_tries_are_shared` now stamps its tries (untimed tries are re-admitted).

**Expected on the host after the merge:** first cycle re-admits the exhausted goals, `next_goal` becomes a real
goal id, `real_queue.selectable` > 0, attempts resume. If baselines still time out they no longer starve the
queue; `gate_timing.json` (in host_main as `real_queue.secs_per_file` / `gate_timeout_s`) shows the
measured cost. Kept rate is still to be measured (2/238 before).

## 1. Dead code to `attic/` — done (reversible)
44 files / 4,158 lines moved with `git mv` (38 modules unreachable from the 177 entry roots and named in no
operational file, plus the 6 test files that only covered them). `attic/MANIFEST.json`, `scripts/attic_restore.py`
(one file or `--all`), or `git revert` the commit. attic is skipped by the import graph, refactor scanner and
kernel ignore; pytest collects `tests/` only. Anything with doubt (100+ modules named in live files, config or
tests that also cover live code) stayed. The bigger list stays in `docs/QUARANTINE_CANDIDATES.md`.

## 2. OS-level jail for gate runs — done (`ETHER_GATE_JAIL=auto`)
`core/agent/gate_jail.py` (see its docstring for the honest limits). Linux: bwrap > unshare > rlimits;
Windows: Job Object (memory, process count, CPU time, kill-on-close, UI limits). Full suite through the gate
path, jail off vs bwrap: 2011 tests, identical verdicts. Windows is mock-tested here and proven on the 1650 by
the self-probe recorded in `host_main.selfcheck.gate_jail`. No network block on Windows by code; the optional
admin rule `scripts/gate_firewall.ps1` targets `ETHER_GATE_PYTHON`. Caveat: a venv `python.exe` on Windows is a
redirector that starts the base interpreter, so a firewall rule on the venv path may not cover the real
process; point `ETHER_GATE_PYTHON` at a dedicated base interpreter for a real block.

## 3. MCP — done, off (`ETHER_MCP=1`)
Real stdio JSON-RPC 2.0 client (`core/agent/mcp_stdio.py`) and a read-only ETHER status server
(`scripts/mcp_status_server.py`). Model-callable only for allowlisted, non-destructive tools.

## 4. LSP — done, off (`ETHER_LSP=1`, `ETHER_LSP_PREGATE=1`)
`core/agent/lsp_client.py`: stdio LSP client (pyright / pylsp / jedi). Read-only `lsp` skill and a pre-gate that
rejects edits adding error diagnostics (no gate run spent; no server = skipped). Tested against a real pylsp.

## 5. Swarm — done, off (`ETHER_SWARM=0|record|1`, `ETHER_GOAL_SCOUTS=1`)
Design study: `docs/SWARM_DESIGN.md` (seven designs ranked for one 4B on the 1650, live-calibrated simulation
`scripts/swarm_sim.py`, results in `docs/results/swarm/`, `tests/test_swarm_sim.py`). Verdict: zero-extra-call
critics + goal-flow scouts first, best-of-2 second; debate / MoA / population rejected.
- Proposer swarm (`core/agent/swarm.py`): one model, K serialized proposals (`model_lock`), CPU workers
  screening in parallel while the next proposal generates, one writer, one unchanged honest gate run per try.
  Default `ETHER_SWARM_K` is **2** (5a).
- Critics in `swarm.screen` (5b): extract, compile, security gem, AST (target must stay a real function, not a
  stub), ruff F821/F811/F823 must not grow, and item 4's LSP diagnostics when `ETHER_LSP_PREGATE=1`.
- `ETHER_SWARM=record` (5c): shadow mode; the critics judge the one normal reply, the same reply is gated, and
  the trajectory records `shadow_would_reject`. `learning_summary.metrics.swarm_shadow.would_reject_kept` > 0
  means a critic would have thrown away a keep.
- Telemetry (5d): `real_kept`, `planted_kept`, `filler_rate_real` (and `real_attempts`, `planted_attempts`,
  `swarm.model_calls`) in `learning_summary.metrics`.
- Goal-flow scouts (5e, `core/agent/scouts.py`, `ETHER_GOAL_SCOUTS=1`): no model calls; weighted round robin by
  source (test_import first, SBFL still gets a slot every cycle), CPU refill (one failing-test shard + lint)
  when fewer than 3 goals are selectable, at most every 10 min.
- Planted goals only when real `selectable` is 0 (5f, no flag).
- `PRODUCT.md`: swarm wording added (opt-in, single-writer, one 4B call at a time; owner decision 2026-11-22,
  audit D1). "Not this product" now names a GPU fan-out swarm and a second writer.

## 6. `docs/AUDIT_TODO.md` — done
All 481 audit items with a status: done 36, done-flag 20, partial 71, open 345, owner 9.

## 7. Docs — done
This file, `docs/FLAGS.md` (batch 10 rows), `STATUS.md`.

## Flags to set on the PC (rollout, docs/SWARM_DESIGN.md)
- Nothing is needed for the idle-host fix (on by default). Keep `ETHER_EXEMPLARS=record`.
- **Phase A** (right after the merge): pregates `ETHER_GEM_PREGATE=1`, `ETHER_LSP_PREGATE=1` (install pylsp or
  pyright in the host venv; no server = no-op); dry-only planted goals `ETHER_PLANTED_GOALS=1` (+
  `ETHER_GOAL_LIVE_ONLY=1`); scouts `ETHER_GOAL_SCOUTS=1`; `ETHER_SAMPLE_TEMP=0,0.7` and `ETHER_DEDUP_REPLY=1`
  (live dup_share 18.5 %). Optional `ETHER_SWARM=record` (no extra model call).
- **Phase B**: `ETHER_SWARM=1` with `ETHER_SWARM_K=2`, only after Phase A has been green for 6 hours or 100 real
  attempts.
- **Kill**: undo the last step if real kept per GPU-hour drops by more than 10 % (or
  `swarm_shadow.would_reject_kept` > 0).

## Apply on the PC
`out/apply-batch10.ps1` (run from the ETHER checkout with the bundle path):
stops the host, fetches origin, verifies the bundle, fetches `ether-batch10`, checks that local-only commits touch
only `artifacts/`, discards local artifact changes, fast-forwards to `origin/main`, merges `ether-batch10`,
pushes (interactive credential prompt allowed), starts the host and prints `supervisor.json` after 90 s.

## What remains
- Measure: kept rate and attempts/day after the fix; `gate_timing.json` secs/file on the 1650.
- `goal_index.json` has no cross-process lock (W47); batch 10 writes more fields into it.
- Owner decisions: swarm default, reviewed host/kept branch (W36/D2), evolution pillar (D4), the rest of the
  quarantine list.
