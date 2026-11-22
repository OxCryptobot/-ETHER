# Batch 9: closing the gaps from the full audit (2026-11-22)

Branch `ether-batch9-gaps` on top of `ether-batch8-rl` (54b0dc92b1); batches 2–9 sit on origin `c8dde296ea`.
Nothing was pushed. Source audit: `docs/AUDIT_FULL_2026-11-22.md` (weakness ids W1…W100).
Every item has its own commit and its own tests (`tests/test_batch9_*.py`). The full suite was run after each
commit and compared test by test with the batch 8 baseline (1957 tests / 1800 pass / 74 fail / 83 skip): no
new failures. The 74 pre-existing failures are unrelated (topology, legacy pipeline defects, two
dashboard_host_first and one p3_54 test).

## 1. Test-weakening route closed (W1, critical) — done
- Model replies can call `search` and `read` only (`skills.MODEL_SKILLS`). `edit`/`test`/`remember` are denied
  with `denied: not a model-callable skill`. `read` is confined to the repo and refuses `.git/`, `.env`,
  `memory/vault`, keys and credential files.
- `edit` refuses `tests/` and `conftest.py` even when called by code.
- `core/agent/tree_guard.py` snapshots the whole tree before an attempt. After the gate, any changed path other
  than the goal file (multi-edit: its file set) turns the verdict into a reject, and every touched path is
  restored (note `rejected: touched …`).
- The audit PoC (one `react()` call edited `tests/test_t.py`) is a regression test, plus an end-to-end test
  through `sota._one`.

## 2. Gate hardening (W4, W5, W6, W35) — done
- The gate and scan pytest runs happen in an incremental mirror (`<tmp>/ether_gate/<hash>`, never inside the
  repo, synced by size+mtime) with a scrubbed environment (no tokens, keys or proxies). `ETHER_GATE_SANDBOX=0`
  runs them in place.
- Per-run timeout `ETHER_GATE_TIMEOUT_S` (180 s). A baseline timeout (or an empty baseline) aborts the attempt
  before the model is asked: reward 0, nothing kept, note `gate aborted: baseline timeout`.
- Tamper detection: after a run, mirror files that differ from the tree, were deleted, or are new `.py` /
  `tests/` files are listed; anything not already present after the baseline run rejects the candidate.
- Wider regression guard: transitive importers (import graph, depth 3) plus a fixed per-goal sample. Measured on
  `core/registry.py`: 35 → 125 guard tests, 6.1 s → 8.8 s.
- Not done (host-only / needs design): an OS-level jail (Windows Job Object / no-network). The sandbox is a copy
  with a scrubbed env, not a security boundary against hostile code.

## 3. Worst-signal health + pull-diverged detector (W2, W33) — done
- `scripts/host_signals.py`: health is the worst of host, pull and pass-rate signals (`ok < degraded < failing`).
  `supervisor.json` gains `health`, `health_worst`, `health_signals`, `pull_failures`. `host_main` reports the
  worst signal and never hides a selfcheck `degraded`.
- Diverged detector (read-only git): when pull fails because local and origin diverged it writes
  `artifacts/pull_diverged.json` with the local-only commits, whether they touch only `artifacts/`, and the
  manual fix `git reset --keep origin/main`. It never resets anything itself. Error text is token-redacted.

## 4. Telemetry out of git (W17, W61) — done
- Publish whitelist cut to 10 small JSON files; the `exe_*` entries are gone (`ETHER_PUBLISH_PATHS=legacy`
  restores the old list). Throttle `PUBLISH_MIN_S` 1800 s. Simulated: ≤ 49 commits/day vs ~5,400 (> 99 % cut).

## 5. Planted-bug goals, no dead-code goals (W10, W12) — done, off by default
- `ETHER_PLANTED_GOALS=1`: when the real queue is empty, a single-site AST mutation of a live function is
  validated in a scratch copy (a test must fail) and served as a goal. Mutations live only in
  `memory/planted/` and scratch dirs; never published or committed. Equivalent mutants are dropped.
- Live files = writer import reachability (145 files). `ETHER_GOAL_LIVE_ONLY=1` skips goals on dead code; new
  seeds on dead code are dropped as `dead_code`. 35 of the 56 failing-test seed goals target dead code.

## 6. Matrix learning view + read-only dashboard (W18, W45) — done
- `unison.py` snapshot gains `learning` (summary, kept rate, arms, dup-reply rate), `health` (worst signal) and
  `capabilities` (model-callable skills). `host_main` publishes it each tick. Read-only.
- `dashboard/app.py`: every non-GET route is refused unless `ETHER_DASHBOARD_WRITE=1`, a 16+ char
  `ETHER_DASHBOARD_TOKEN` matches `X-Ether-Token`, and Host/Origin are localhost.

## 7. Gem bugs + contracts — done
- Grandidierite extension template braces escaped; Rose Quartz stream path returns an error on empty content.
  The two failing gem contract tests now pass; new contract tests added.

## 8. Docs — done
- `STATUS.md` rewritten; `docs/FLAGS.md` is the one table of batch 2–9 flags; `:8787` removed from operational
  docs (dated audits and ADR 0003 left as history). `PRODUCT.md` untouched; the swarm question is open.
- `docs/QUARANTINE_CANDIDATES.md`: 413 unreachable modules (59.5k lines) listed, nothing moved or deleted.

## 9. Pillar wiring — partial, off by default
- `ETHER_GEM_PREGATE=1`: the Black Tourmaline security gem sits between `apply_edit` and the gate, with no model
  call. An edit that adds a shell, eval/exec, dynamic import, socket or rmtree is restored and fed back without
  a gate run. It can only reject.
- Not wired: swarm (owner decision), MCP, LSP, multi-model routing. The other gems stay adapters.

## Flags to set on the PC
- `ETHER_EXEMPLARS=record` (from batch 7). Everything else is fine at its default.
- When the real queue is dry: `ETHER_GOAL_LIVE_ONLY=1` and `ETHER_PLANTED_GOALS=1`.
- If `learning_summary.json` shows duplicate replies ≥ 15 %: `ETHER_SAMPLE_TEMP=1` (+ `ETHER_DEDUP_REPLY=1`).
- Optional: `ETHER_GEM_PREGATE=1`.

## Apply on the PC (owner, by hand)
```bat
cd C:\path\to\ETHER
scripts\host.cmd stop
git fetch origin
git fetch C:\path\to\ether-batch9.bundle ether-batch9-gaps:ether-batch9-gaps
git log origin/main..HEAD --name-only        &REM every local-only commit must touch only artifacts/
git reset --keep origin/main                 &REM only after the check above
git merge --ff-only ether-batch9-gaps        &REM if not ff: git merge ether-batch9-gaps
git push origin main
set ETHER_EXEMPLARS=record                   &REM or setx / the host env file
scripts\host.cmd start
```
Then check `artifacts/supervisor.json`: `health_worst` should be `ok` and `pull_failures` 0 after a cycle.

## What remains
- Owner decisions: swarm vs `PRODUCT.md`; dead-code quarantine (list ready); a reviewed host branch for kept
  edits (W36); exploration default.
- Host-only: the one-time `reset --keep` + push; an OS-level jail for gate runs; confirming the live publish
  rate drops after the push.
