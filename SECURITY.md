# Security Policy

## Reporting
If you find a vulnerability in @ETHER, open a private security advisory on the repo or contact the maintainers directly. Do not file a public issue for exploitable bugs.

## Security model (summary)
- LLM output is untrusted until it passes sandbox + audit
- Primary isolation boundary is Docker: `--network none`, `--read-only`,
  `--user 65534:65534`, `--cap-drop ALL`, `--security-opt no-new-privileges`,
  `--pids-limit`, memory/CPU limits, writable `/tmp` tmpfs only
- An explicit `ETHER_SANDBOX_BACKEND=docker` fails closed. It will NOT silently
  fall back to host execution when Docker is unavailable; only `auto` may
  degrade, and it flags `sandbox_fallback:local` when it does
- AST + regex checks are defense-in-depth only
- Self-generated tools stay in `tools/quarantine/` until explicitly promoted.
  `resolve_tool` never executes from quarantine, and `tool_reconcile` promotion
  requires `ETHER_AUTO_PROMOTE=1` plus a static-safety and audit pass
- The audit gate rejects on **any** policy violation, not on a risk threshold
- Verification counts only assertions that could actually fail (AST-parsed;
  tautologies, dead branches, swallowed failures and self-reported stdout
  counts do not count) — see `core/assert_audit.py`
- Orchestrator enforces retry and loop caps to prevent runaway extension

## Known weaknesses (do not assume these are covered)
- `ETHER_SANDBOX_BACKEND=local` runs model code with host Python and provides
  **no** isolation. It is opt-in and should be treated as trusted-input-only.
- `core/patch_loop.py` writes into the working tree with `git apply` and runs
  scratch tests on the host, outside any container. It is gated to
  `memory/scratch` by path resolution and is opt-in via `ETHER_PATCH_LOOP=1`.
- The dashboard's `/api/promote` and `/api/reconcile-tools` endpoints are
  unauthenticated; bind the dashboard to localhost only.
- Retrieved memory and curriculum files are model-influenced inputs that are
  re-injected into later prompts; they are not sanitized.

## Non-goals
- Formal verification
- Protection against a compromised Docker host
- Guaranteeing model outputs are always correct
