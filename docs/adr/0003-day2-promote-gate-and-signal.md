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
- **`ether promote` (CLI) routes through the same gate (review fix m1).**
  It was a raw copy with no gate and no filename normalization (absolute /
  `..` filenames read outside quarantine). Now the filename is normalized
  with `Path(filename).name`, rejected unless it matches
  `^[A-Za-z0-9_\-]+\.py$` (error + non-zero exit), and the copy only runs
  after `_promotion_gate(src, operator_initiated=True)` — a CLI invocation
  is an explicit operator action, the same consent class as the click.
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
- **Every launcher defaults pushes off (review fix B1).** Day 2 changed only
  `run_smart_cycle.py`'s setdefault — but the daemon was never launched
  bare: `ensure_daemon.ps1` (via `autonomy-host.yml`), `start_daemon.ps1`,
  `stabilize.ps1` and `desktop_launch.ps1` each HARD-set
  `$env:ETHER_FLYWHEEL_PUSH = "1"` before spawn, and `ether_daemon.py` /
  `desktop_runtime.py` `setdefault(..., "1")`, so the child inherited a
  forced `"1"` and Day 2's `setdefault(..., "0")` was a no-op on the real
  daemon chain. All launchers now default the flag to `"0"` only when unset
  (the PowerShell launchers additionally peek at `.env` first — an
  already-set `"0"` would shadow a `.env` opt-in, since `core/dotenv.py`
  never overrides set variables), `ether_daemon.py`/`desktop_runtime.py`
  setdefault `"0"`, and `.env.example` documents the opt-in commented out.

## Consequences

- The dashboard promote button now runs static_safety + the Black
  Tourmaline audit on every click — slower (a registry build per promote)
  but fail-closed; a broken audit dependency now refuses promotion instead
  of waving it through. The `ether promote` CLI takes the same route: a CLI
  invocation IS an explicit operator action (same consent class as the
  dashboard click), the filename is normalized to a basename and rejected
  unless it matches `^[A-Za-z0-9_\-]+\.py$`, and gate refusal exits
  non-zero.
- Report pushes now default OFF end-to-end. The pre-fix mechanism was NOT
  the previously-assumed "deliberate opt-in by the daemon operator": the
  PowerShell/python launchers force-set `ETHER_FLYWHEEL_PUSH=1` into the
  daemon's inherited environment, so `run_smart_cycle.py`'s
  `setdefault(..., "0")` never fired in the child. After fix B1 every
  launcher defaults the flag off, and the daemon loop produces local-only
  reports unless the operator opts in — the opt-in lives solely in
  `.env`/the environment (`ETHER_FLYWHEEL_PUSH=1`).
- One explicit opt-in fallback remains, deliberately:
  `scripts/ether_daemon.py` falls back to `cli.main flywheel --push` only
  when `scripts/run_smart_cycle.py` is missing — i.e. a broken install —
  and the explicit flag still forces a push there. It is left intact as
  the documented escape hatch; the normal daemon path never reaches it.
- **Cycle duration vs daemon cadence (MEAS-002 tradeoff).** Raising the
  pytest step 300→900 means a worst-case cycle (reinstall 300 + smoke 120 +
  pytest ≤900 + doctor 60 + batch tick 600 + agentic retries) can exceed
  both daemon intervals (`ensure_daemon.ps1` sets 300s, the daemon default
  is 900s) and the 15-min `autonomy-host.yml` cron spacing. Both loops are
  sequential (sleep-after-cycle), so there is no self-overlap; the effects
  are a slower effective cadence and possibly queued workflow runs on the
  single self-hosted runner. The full suite is kept over a smoke subset
  because the pytest result IS the flywheel's quality signal — a subset
  would fake green.
- Branch protection on main (required reviewers/status checks so report
  bots cannot push directly) is a GitHub settings action for the user — it
  is documented here because it cannot be expressed in code.
- No new `os.getenv` sites were added (QUAL-005 count unchanged from the
  post-Day-1 baseline).

## Residuals

- Quarantine files are still plain text in the repo; a quarantined tool's
  content is visible to anyone with read access. Encryption/ACLs are a
  later-stage decision.
- The dashboard has no auth: uvicorn binds 127.0.0.1:8787 and
  `POST /api/promote` is unauthenticated, so `operator_initiated=True`
  consent is spoofable by ANY local process — the consent distinction is
  not the barrier. The real barrier is the static_safety + Black
  Tourmaline audit that runs on every promote regardless of consent mode.
  Exposure is further bounded by the fact that quarantined model-authored
  code cannot reach the endpoint directly: it only ever executes via
  sandbox/compile paths, never as a host process, so the spoofing surface
  is limited to code already running on the host. Token auth for mutating
  dashboard endpoints is a deliberate deferral under the solo-dev
  localhost posture, not an oversight.
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
