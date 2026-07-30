# ADR 0003: Day-2 Promote Gate Fail-Closed + Flywheel Signal Rebase (ETHER roadmap, day 2 of 5)

## Status

Accepted — Day 2 of 5 of the security hardening roadmap. Closes audit
findings SEC-001/S-02 (promote paths bypass the safety gate), SEC-002
(resolve_tool quarantine claim defeated by traversal), SEC-005 (Black
Tourmaline pattern gaps), MEAS-002 (flywheel pytest timeout below the suite
mean) and MEAS-005 (flywheel report-commit flood on main).

## Context

- **SEC-001/S-02 (gate bypass):** `POST /api/promote` copied
  quarantine→persistent with only a filename regex — no static_safety, no
  Black Tourmaline audit — while the daemon reconcile path was gated behind
  `ETHER_AUTO_PROMOTE=1`. The single human-clickable path was the least
  checked one.
- **SEC-002 (traversal):** `resolve_tool` appended `.py` and returned
  `PERSISTENT / name`; `name="../quarantine/evil"` resolved outside
  PERSISTENT and `run_tool` would execute it, contradicting the docstring's
  "Only PERSISTENT is searched".
- **SEC-005 (pattern gaps):** the tourmaline forbidden list matched
  `subprocess.call|run|Popen` but not `check_output`/`check_call`,
  `os.popen(` or `socket.socket(` — unaudited execution/egress channels
  through the only audit gate in the system. `promote_safe.py`'s RISKY
  regex had the same gaps, plus a `force=true` escape hatch.
- **MEAS-002 (perpetual 0/0):** the flywheel pytest step ran with
  `timeout=300` while the suite mean is ~379.5s on the autonomy host, so
  every cycle timed out and reported 0/0.
- **MEAS-005 (report flood):** `--autonomous` implied `do_push=True`,
  producing ~25 flywheel report commits/24h to main. Autonomy was treated
  as consent to publish.

## Decision

- **Two-mode gate consent.** `_promotion_gate(path, *, operator_initiated=False)`:
  the daemon path consents via `ETHER_AUTO_PROMOTE=1` (unchanged); an
  explicit human action (`operator_initiated=True`) IS the consent and
  skips ONLY the env check. Unreadable-file, static_safety and Black
  Tourmaline audit checks still run and still fail CLOSED (any exception →
  `{"ok": False, ...}`).
- **`/api/promote` routes through the gate.** After the 400/404 checks and
  before `shutil.copy2`, the handler calls
  `tool_reconcile._promotion_gate(src, operator_initiated=True)` and raises
  403 on refusal. Destination-name logic, mkdir and copy are byte-identical.
- **Traversal close.** `resolve_tool` restricts stems to `[A-Za-z0-9_-]+`
  and verifies `path.resolve().parent == PERSISTENT.resolve()`; `..`,
  subdirectory and percent-encoded names return None. `run_tool` unchanged.
- **Pattern extension.** Black Tourmaline gains
  `check_output|check_call` on the subprocess pattern plus `os\.popen\s*\(`
  and `socket\.socket\s*\(`. Note the deliberate false positive:
  `socket.socket(` also matches benign networking code (e.g. a health
  probe); we accept review friction on quarantined, self-fabricated code —
  the gate is the last review before host execution, so over-flagging is
  the safe side. `promote_safe.py`'s RISKY regex is aligned to the same set
  and the `force=true` override is removed: risky code is refused
  unconditionally ("no override").
- **Timeout 900.** The flywheel pytest step gets `timeout=900`, above the
  ~380s suite mean, so cycles produce a real pass/fail signal again.
- **Push decoupling.** `flywheel._compute_do_push(push_flag)` returns
  `push_flag or ETHER_FLYWHEEL_PUSH == "1"`; `main()` no longer lets
  `--autonomous` imply push. `run_smart_cycle.py` defaults
  `ETHER_FLYWHEEL_PUSH` to `"0"` instead of `"1"`.

## Consequences

- The dashboard promote button now runs static_safety + the Black
  Tourmaline audit on every click — slower (a registry build per promote)
  but fail-closed; a broken audit dependency now refuses promotion instead
  of waving it through.
- Operators who want report publishing back must set
  `ETHER_FLYWHEEL_PUSH=1` (or pass `--push`). `scripts/ether_daemon.py`
  still launches the flywheel with an explicit `--push`, which is a
  deliberate opt-in by the daemon operator and is unchanged.
- Branch protection on main (required reviewers/status checks so report
  bots cannot push directly) is a GitHub settings action for the user — it
  is documented here because it cannot be expressed in code.
- No new `os.getenv` sites were added (QUAL-005 count unchanged from the
  post-Day-1 baseline).

## Residuals

- Quarantine files are still plain text in the repo; a quarantined tool's
  content is visible to anyone with read access. Encryption/ACLs are a
  later-stage decision.
- The dashboard has no auth; binding to localhost (127.0.0.1:8787) is the
  existing posture and remains the mitigation — the promote gate assumes
  "whoever can click is the operator".
- `socket.socket(` false positives (above) are accepted, not tuned away.

## Rollback

Revert the Day-2 commits (`migration(day2): …`). The gate parameter is
keyword-only with a default preserving Day-1 behavior, so partial reverts
of the dashboard/registry/tourmaline changes do not break the reconcile
path.

## Roadmap fit

Doc 1 §7 Day 2: "Promote gate: /api/promote routes through _promotion_gate
(fail-closed); resolve_tool sanitization; Black Tourmaline patterns
extended; force=true removal. Flywheel signal: pytest timeout above suite
mean; report commits to main stop." All six items land here; Day 3 picks up
the sandbox/quarantine moves.
