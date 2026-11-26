# @ETHER Status

**Updated:** 2026-11-26 (batch 10, branch `ether-batch10`, unpushed; batches 2–9 are live on origin main). This file describes the code,
not the live host. Live truth: `artifacts/supervisor.json` (health = worst signal), `artifacts/host_main.json`,
`artifacts/learning_summary.json` and `artifacts/unison.json` on origin.

## Law
Single writer: `scripts/host_main.py` under `scripts/host_supervisor.py` (no ETHER.exe). The Grok Control
Matrix is read-only. Tool-first. Honest gate only: tool edit + target test pass + 0 regressions; a
generate-fallback is never a pass. GTX 1650 + `qwen3.5:4b`, NUM_CTX 4096. No second installer; updates by
`git pull`. Learning only from the honest gate's 0/1 reward.

## What batches 2–10 changed (2–9 live; 10 unpushed until the owner applies it)
- 2–3: real goals from failing tests + lint; filler retired; regression revert; publish clobber guard.
- 4: Thompson-sampling arms with posterior promotion. 5: SBFL b5, multi-edit (off), selfcheck, smoke, NUM_CTX.
- 6: span goals, gem contract tests. 7: exemplars (off / record / 1). 8: sampling temperature + dedup (off).
- 9: closes the audit's critical gaps: read-only model tools + whole-tree gate check (test-weakening route
  closed), sandboxed + scrubbed gate runs, timeout aborts, wider regression guard, worst-signal health and a
  pull-diverged detector, telemetry whitelist + 30 min throttle, planted-bug goals (off), Matrix learning
  view, read-only dashboard, two gem bugs fixed, security-gem pre-gate (off). Details: `docs/BATCH9.md`. Flags: `docs/FLAGS.md`.
- 10: the live host had been idle since 2026-11-24 21:14Z: baseline timeouts (fixed 180 s vs the wider batch 9
  guard on the 1650) spent tries without a model call until every open goal was exhausted, while health said
  "queue empty" next to 95 open goals. Fixed: aborts spend no try (backoff + trimmed guard), the gate timeout
  follows measured time, exhausted goals are re-admitted, health names why goals are skipped. Also: OS jail
  for gate runs (auto), MCP + LSP clients (off), proposer swarm (off), 44 dead files to `attic/`,
  `docs/AUDIT_TODO.md`. Details: `docs/BATCH10.md`.

## Open owner decisions
- Swarm: batch 10 built the doctrine-compatible version (one model, serialized calls, CPU screens, one writer),
  `ETHER_SWARM` default off. Turning it on, and whether `PRODUCT.md` needs a wording change, is open.
- Dead code: 44 provably unreachable files moved to `attic/` (batch 10, reversible); the larger candidate list in
  `docs/QUARANTINE_CANDIDATES.md` is still an owner decision.
- Host/kept branch for reviewed pushes of kept edits (audit W36): open.
- `ETHER_SOTA_EXPLORE=0` (training wheels) turns exploration off: open.

## Host-only steps
Apply batch 10 with `apply-batch10.ps1` (docs/BATCH10.md "Apply on the PC"). Then check `host_main.json`:
`next_goal` is a goal id, `real_queue.selectable` > 0, and `supervisor.json` `health_worst` no longer says
"queue empty".
