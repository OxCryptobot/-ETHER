# ETHER writer flags (batches 2–10)

One table for every environment flag added or changed in batches 2–10 (branch `ether-batch10` on top of
`ether-batch9-gaps`; batch 9 is live on `origin/main`). Defaults are the code's defaults: a flag you do not set keeps
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
| `ETHER_GATE_TIMEOUT_SCALE` | `1` | 10.0 | gate/budget | Gate/baseline timeout = max(`ETHER_GATE_TIMEOUT_S`, margin x measured secs per test file x files) x 1.5 per earlier baseline abort of the goal. `0` = fixed 180 s (batch 9). Measurements: `artifacts/gate_timing.json`. |
| `ETHER_GATE_TIMEOUT_MARGIN` / `ETHER_GATE_TIMEOUT_MAX_S` | `2.0` / `900` | 10.0 | gate/budget | Safety margin over the measured time; hard cap per pytest run. |
| `ETHER_ABORT_BACKOFF_S` / `ETHER_ABORT_MAX` | `1800` / `6` | 10.0 | outcome | A baseline that cannot run (timeout, sandbox error, no results) spends no try; the goal waits 1800 s x 2^(n-1) (max 24 h) and is parked after 6 aborts (shown in health). |
| `ETHER_GUARD_TRIM` | `1` | 10.0 | gate/budget | After a baseline abort the goal's guard keeps its test file + direct importers and halves the transitive/smoke/sample extras per abort. `0` = never trim. |
| `ETHER_GOAL_RETRY_S` / `ETHER_GOAL_MAX_ROUNDS` | `172800` / `2` | 10.0 | outcome | An exhausted goal (MAX_TRIES, or its SBFL cluster at MAX_TARGET_TRIES) gets a fresh round after 48 h x 2^round, at most 2 extra rounds. Pre-batch-10 tries carry no timestamp and are re-admitted once. `ETHER_GOAL_RETRY_S=0` = never (batch 9). |
| `ETHER_GATE_JAIL` | `auto` | 10.2 | gate | OS jail for gate/scan pytest: Linux bwrap > unshare > rlimits; Windows Job Object. `1` = required (refuse the run if no backend), `0` = off. |
| `ETHER_GATE_JAIL_MEM_MB` / `ETHER_GATE_JAIL_PROCS` / `ETHER_GATE_JAIL_CPU_S` | `4096` / `64` / from timeout | 10.2 | gate | Jail caps: address space / job memory, active processes, CPU seconds. |
| `ETHER_GATE_JAIL_NET` | `0` | 10.2 | gate | `1` lets jailed runs use the network (default: none where the backend can block it; Windows cannot). |
| `ETHER_GATE_PYTHON` | unset | 10.2 | gate | Dedicated interpreter for gate runs (pair with the optional `scripts/gate_firewall.ps1` rule). |
| `ETHER_MCP` / `ETHER_MCP_TIMEOUT_S` / `ETHER_MCP_MAX_CHARS` | `0` / `15` / `1200` | 10.3 | outcome | Read-only `mcp` skill for the model (stdio JSON-RPC client; `scripts/mcp_status_server.py` = ETHER status server). |
| `ETHER_LSP` / `ETHER_LSP_CMD` / `ETHER_LSP_TIMEOUT_S` | `0` / auto / `20` | 10.4 | outcome | Read-only `lsp` skill (diagnostics / definition / references); server: `ETHER_LSP_CMD` > pyright-langserver > pylsp > jedi-language-server. |
| `ETHER_LSP_PREGATE` | `0` | 10.4 | outcome | Reject (restore, no gate run) an edit that adds error diagnostics to the goal file. No server / timeout = skipped. Can only reject. |
| `ETHER_SWARM` | `0` | 10.5 | outcome | `0` off; `record` = shadow: the swarm's CPU critics judge the one normal reply and log `shadow_would_reject`, nothing changes; `1` = K serial proposals from the one model, screened by CPU workers in parallel, best one gated (K model calls per try). |
| `ETHER_SWARM_K` / `ETHER_SWARM_TEMP` / `ETHER_SWARM_WORKERS` / `ETHER_SWARM_LOCKFILE` | **`2`** / `0.7` / `2` / `1` | 10.5 | outcome | Candidates per try (max 4; raise to 3 only after a green K=2 A/B), temperature of candidates 2..K, CPU screen workers, cross-process `artifacts/model.lock`. |
| `ETHER_SWARM_AST` | `1` | 10.5 | outcome | Swarm/record critic: target must stay a real function (no pass / ... / NotImplementedError) and ruff F821/F811/F823 must not grow. LSP critic per candidate follows `ETHER_LSP_PREGATE`. |
| `ETHER_GOAL_SCOUTS` | `0` | 10.5 | outcome | Goal-flow scouts, no model calls: weighted round robin by source (test_import first, SBFL never starved) and a CPU refill (failing-test shard + lint) when few goals are selectable. |
| `ETHER_SCOUT_PATTERN` / `ETHER_SCOUT_MIN_SELECTABLE` / `ETHER_SCOUT_EVERY_S` / `ETHER_SCOUT_FILES` | `test_import,test_import,sbfl,import_error,test_import_assign,lint` / `3` / `600` / `16` | 10.5 | outcome | Scout order, refill threshold, refill cooldown, test files per refill shard. |

Always on in batch 9 (security, stricter only, no flag): model replies can call only `search` and
`read`; the gate rejects any diff outside the goal file (tests/ immutable) and restores every
touched path; credentials and proxies are scrubbed from every gate/scan run.

Recommended host start (Phase 0, after the batch 9 push): `ETHER_EXEMPLARS=record`; leave every
other outcome flag at its default until `first_hour_report` at +1 h and +6 h says otherwise
(dup-reply >= 15% -> `ETHER_SAMPLE_TEMP=0,0.7`; queue empty -> `ETHER_PLANTED_GOALS=1` and
`ETHER_GOAL_LIVE_ONLY=1`).

## Batch 10 rollout (docs/SWARM_DESIGN.md)

Item 0 (idle-host fix) is on by default and needs no flag. Planted goals are served only when real
`selectable` is 0 (batch 10, no flag). Measure with `first_hour_report` and `learning_summary.metrics`
(`real_kept`, `planted_kept`, `filler_rate_real`, `kept_per_gpu_hour`, `swarm_shadow`).

- **Phase A** (right after the merge): pregates `ETHER_GEM_PREGATE=1` and `ETHER_LSP_PREGATE=1` (pylsp or
  pyright in the host venv; without a server it is a no-op), dry-only planted goals `ETHER_PLANTED_GOALS=1`
  (+ `ETHER_GOAL_LIVE_ONLY=1`), scouts `ETHER_GOAL_SCOUTS=1`, `ETHER_SAMPLE_TEMP=0,0.7` and
  `ETHER_DEDUP_REPLY=1`. Optional: `ETHER_SWARM=record` (shadow critics, no extra model call). Keep
  `ETHER_EXEMPLARS=record`.
- **Phase B**: `ETHER_SWARM=1` with `ETHER_SWARM_K=2`, only after Phase A has been green for 6 hours or
  100 real attempts (queue flowing, health never "empty" with open goals, `swarm_shadow.would_reject_kept`
  = 0, kept/attempt not below the Phase A rate).
- **Kill**: turn the last flag off again if real kept per GPU-hour drops by more than 10 % against the
  previous phase (or any would-reject turns out to be a keep).
