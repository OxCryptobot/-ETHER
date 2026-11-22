# @ETHER Status

**Updated:** 2026-11-22 (batch 9, branch `ether-batch9-gaps`, unpushed). This file describes the code,
not the live host. Live truth: `artifacts/supervisor.json` (health = worst signal), `artifacts/host_main.json`,
`artifacts/learning_summary.json` and `artifacts/unison.json` on origin.

## Law
Single writer: `scripts/host_main.py` under `scripts/host_supervisor.py` (no ETHER.exe). The Grok Control
Matrix is read-only. Tool-first. Honest gate only: tool edit + target test pass + 0 regressions; a
generate-fallback is never a pass. GTX 1650 + `qwen3.5:4b`, NUM_CTX 4096. No second installer; updates by
`git pull`. Learning only from the honest gate's 0/1 reward.

## What batches 2–9 changed (all unpushed until the owner pushes)
- 2–3: real goals from failing tests + lint; filler retired; regression revert; publish clobber guard.
- 4: Thompson-sampling arms with posterior promotion. 5: SBFL b5, multi-edit (off), selfcheck, smoke, NUM_CTX.
- 6: span goals, gem contract tests. 7: exemplars (off / record / 1). 8: sampling temperature + dedup (off).
- 9: closes the audit's critical gaps: read-only model tools + whole-tree gate check (test-weakening route
  closed), sandboxed + scrubbed gate runs, timeout aborts, wider regression guard, worst-signal health and a
  pull-diverged detector, telemetry whitelist + 30 min throttle, planted-bug goals (off), Matrix learning
  view, read-only dashboard, two gem bugs fixed, security-gem pre-gate (off). Details: `docs/BATCH9.md`. Flags: `docs/FLAGS.md`.

## Open owner decisions
- Swarm vs `PRODUCT.md` ("Not this product: ... a swarm"): open; no swarm code was written.
- Dead code (35 of the 56 failing-test seed goals target modules the writer never imports): not deleted; see
  `docs/QUARANTINE_CANDIDATES.md`.
- Host/kept branch for reviewed pushes of kept edits (audit W36): open.
- `ETHER_SOTA_EXPLORE=0` (training wheels) turns exploration off: open.

## Host-only steps
The host clone was diverged (pull rc 128 every cycle). Fix once by hand, then push batch 9; see
`docs/BATCH9.md` "Apply on the PC". The supervisor now reports this itself (`pull_diverged.json`).
