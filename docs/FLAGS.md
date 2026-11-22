# ETHER writer flags (batches 2–9)

One table for every environment flag added or changed in batches 2–9 (branch `ether-batch9-gaps`,
base `origin/main` @ `c8dde296ea`). Defaults are the code's defaults: a flag you do not set keeps
the safe choice. Set flags in the host environment that `scripts\host.cmd start` inherits (user
environment variables on the 1650), then restart the supervisor.

Legend: **on/off** = default; *gate* = only makes the honest gate stricter (default-on is allowed);
*outcome* = can change which edits are tried or kept (default = batch 8 behaviour).

| Flag | Default | Batch | Kind | What it does |
|---|---|---|---|---|
| `ETHER_GOAL_SOURCE` | `1` | 2 | outcome | Real goals from failing tests + lint (`0` = legacy ladder only). |
| `ETHER_GOAL_GUARD` | `1` | 2 | gate | Goal-quality guard: filler, constant tests, spoilers, protected targets are refused. |
| `ETHER_SOTA_LEGACY` | unset | 2 | outcome | `1` brings the retired legacy ladder back. |
| `ETHER_REFACTOR` | `0` | 2/6 | outcome | Rule-based refactor goals (remove_filler, dead_code, dedent_snippet, state_writer). |
| `ETHER_GOAL_SCAN` / `_S` / `_FILES` | `1` / `900` / `8` | 2 | outcome | Refresh one shard of the failing-test index every 900 s or when dry. |
| `ETHER_REAL_PER_TICK` | `2` | 2 | outcome | Max real-goal attempts per writer pass. |
| `ETHER_GUARD_SUITE` | unset | 2 | gate | `full` = run the whole suite as the regression guard (slow on the 1650). |
| `ETHER_EDIT_CONSTANTS` | `1` | 3 | outcome | Edits may replace/add module-level assignments with the function. |
| `ETHER_SBFL` | `1` | 3 | outcome | Spectrum fault localisation during scans. |
| `ETHER_SBFL_RANK` | `b5` | 5 | outcome | SBFL ranking (b5 resolves dispatchers to the handler reached). |
| `ETHER_SOTA_EXPLORE` | unset | 3/4 | outcome | Real goals explore arms unless `0`; legacy only if `1`. `0` turns learning-by-exploration off (training-wheels conflict, owner decision). |
| `ETHER_BANDIT` | `thompson` | 4 | outcome | Arm selector (`thompson`, `ucb1`, `eps`, ...). |
| `ETHER_BANDIT_ARMS` | REAL_ARMS | 4 | outcome | Comma list of arms. |
| `ETHER_BANDIT_GAMMA` | `1.0` | 4 | outcome | Discount for non-stationary arms (e.g. `0.98`). |
| `ETHER_BANDIT_COST` | `0` | 4 | outcome | Pick by pass rate per GPU-second. |
| `ETHER_BANDIT_FACTORED` | `0` | 4 | outcome | Factored arms (`f:` prefix). |
| `ETHER_PROMOTE_RULE` | `posterior` | 4 | outcome | Arm promotion rule. |
| `ETHER_NEURO_ES` | `0` | 4 | outcome | Evolution-strategy arm proposals (never promotes by itself). |
| `ETHER_MULTI_EDIT` | `0` | 5 | outcome | Transactional multi-target edits (<= 3 places, FileTx all-or-nothing). |
| `ETHER_NUM_CTX` | `4096` | 5 | budget | Ollama context window (GTX 1650 + qwen3.5:4b). |
| `ETHER_REPLY_MAX` | `768` | 5 | budget | Reply token cap. |
| `ETHER_SMOKE` / `ETHER_SMOKE_TIMEOUT_S` | `1` / `300` | 5 | safety | Post-pull smoke test in the supervisor. |
| `ETHER_PULL_ROLLBACK` | `0` | 5 | safety | On a failed smoke, local `reset --keep` to the last good commit + pin. |
| `ETHER_IDLE_MAX_S` | `900` | 5 | budget | Cap for the empty-queue backoff. |
| `ETHER_SPAN_EDIT` | `1` | 6 | outcome | Span goals (marked window) for too-large targets. |
| `ETHER_EXEMPLARS` | `0` | 7 | outcome | `record` = store gate-kept diffs (never injected); `1` = also the `exemplar` arm. |
| `ETHER_SAMPLE_TEMP` | unset | 8 | outcome | Try-indexed temperature, e.g. `0,0.7` (turn on only if duplicate replies >= 15%). |
| `ETHER_DEDUP_REPLY` | `0` | 8 | outcome | Skip a reply the gate already reverted on the same file state. |
| `ETHER_GATE_SANDBOX` | **`1`** | 9 | gate | Gate/scan pytest runs in a synced copy outside the repo; tamper beyond the baseline = reject. `0` = in place (env still scrubbed). |
| `ETHER_GATE_SANDBOX_DIR` | tempdir/ether_gate | 9 | infra | Where sandbox copies live (never inside the repo). |
| `ETHER_GATE_TIMEOUT_S` | `180` | 9 | gate | Per-run pytest timeout; a timed-out baseline aborts the attempt, a timed-out after-run is never a pass. |
| `ETHER_GUARD_TRANSITIVE` | **`1`** | 9 | gate | Guard adds transitive importers + a fixed sample (`0` = batch 8 selection). |
| `ETHER_GUARD_DEPTH` | `2` | 9 | gate | Import hops for transitive selection. |
| `ETHER_GUARD_MAX_AFFECTED` | `10` | 9 | gate/budget | Max importer test files in the guard. |
| `ETHER_GUARD_SAMPLE` / `ETHER_GUARD_SAMPLE_MAX_BYTES` | `3` / `24000` | 9 | gate/budget | Fixed per-goal random sample of small test files. |
| `ETHER_HEALTH_PULL_FAILING` | `3` | 9 | health | Consecutive failed pulls before health = failing. |
| `ETHER_HEALTH_SOTA_STALE_S` | `21600` | 9 | health | No learning attempt for this long = degraded. |
| `ETHER_HEALTH_HOST_STALE_S` | `7200` | 9 | health | host_main.json older than this = degraded (supervisor view). |
| `ETHER_PUBLISH_MIN_S` | **`1800`** (was 300) | 5/9 | telemetry | Heartbeat-only commits at most every 30 min; kept code still urgent. |
| `ETHER_PUBLISH_PATHS` | unset | 9 | telemetry | `legacy` = batch 8 publish list (minus exe_*) for debugging. |
| `ETHER_PLANTED_GOALS` | `0` | 9 | outcome | When the real pool is dry, attempt validated planted bugs in a scratch copy (never published). |
| `ETHER_PLANTED_CANDIDATES` | `4` | 9 | budget | Candidate bugs validated per generation round. |
| `ETHER_PLANTED_DIR` | tempdir/ether_planted | 9 | infra | Scratch workspace for planted goals (never inside the repo). |
| `ETHER_GOAL_LIVE_ONLY` | `0` | 9 | outcome | Drop real goals (and new seeds) whose target the writer never imports (35 of the 56 failing-test seed goals). |
| `ETHER_GEM_PREGATE` | `0` | 9 | outcome | Black Tourmaline (security gem) rejects an edit that adds subprocess/os.system/eval/exec/`__import__`/socket/rmtree/import_module to the goal file before the gate runs (restored, reward as any failed reply). Can only reject. |
| `ETHER_DASHBOARD_WRITE` + `ETHER_DASHBOARD_TOKEN` | unset | 9 | security | Retired dashboard refuses all writes unless both are set (token >= 16 chars, localhost only). |

Always on in batch 9 (security, stricter only, no flag): model replies can call only `search` and
`read`; the gate rejects any diff outside the goal file (tests/ immutable) and restores every
touched path; credentials and proxies are scrubbed from every gate/scan run.

Recommended host start (Phase 0, after the batch 9 push): `ETHER_EXEMPLARS=record`; leave every
other outcome flag at its default until `first_hour_report` at +1 h and +6 h says otherwise
(dup-reply >= 15% -> `ETHER_SAMPLE_TEMP=0,0.7`; queue empty -> `ETHER_PLANTED_GOALS=1` and
`ETHER_GOAL_LIVE_ONLY=1`).
