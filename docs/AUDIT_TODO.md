# AUDIT_TODO: every item of docs/AUDIT_FULL_2026-11-22.md, with status after batch 10

Generated 2026-11-26 from the audit (481 items: 100 weaknesses, 100 improvements, 50 features, 12 x 25 deep-dives, 6 owner decisions).
Status is code-verified for the batch that is named; an item without a named batch is `open` (not built, or not verified).

* `done`: built and on by default (or a fix with no flag).
* `done-flag`: built and tested, default off (docs/FLAGS.md).
* `partial`: part of the item exists; the note says what is missing.
* `open`: not built.  `owner`: needs an owner decision.

**Totals (481):** done 36, done-flag 19, open 345, owner 10, partial 71


Weaknesses (sec. 5): done 12, done-flag 3, open 59, owner 2, partial 24

## Weaknesses (sec. 5)

| id | item | status | evidence / batch |
|---|---|---|---|
| W1 | Model output can edit any repo file and run arbitrary code through the live ReAct tool router (audit line 122) | done | batch 9 |
| W2 | Host clone is diverged; supervisor pull fails every cycle, so the batch 7 push will not land (audit line 133) | done | batch 9 detector; host pull ok, pull_failures 0 (live 2026-11-26) |
| W3 | The live host makes zero learning progress (audit line 144) | partial | batch 10 item 0 removes the idle cause (queue starved by baseline-timeout aborts); kept rate 2/238 still unmeasured after the fix |
| W4 | 'Verified Execution: every artifact sandboxed' is false on the live path (audit line 155) | partial | batch 9 mirror + scrubbed env; batch 10 item 2 OS jail (bwrap/unshare/rlimits, Windows Job Object); no network block on Windows |
| W5 | Regression guard sees 2-4% of the suite (audit line 166) | done | batch 9 |
| W6 | A baseline timeout silently turns the regression gate off (audit line 177) | done | batch 9 abort; batch 10 item 0: abort no longer burns tries, timeout scales with measured time |
| W7 | Finite curriculum: the goal pool runs dry in hours (audit line 188) | done-flag | batch 9 planted goals (ETHER_PLANTED_GOALS=1); batch 10 item 0 re-admits exhausted goals |
| W8 | Every real attempt is greedy (temperature 0) (audit line 199) | done-flag | batch 8 ETHER_SAMPLE_TEMP + dedup; batch 10 swarm samples K candidates (ETHER_SWARM=1) |
| W9 | Kept edits are forgotten: no memory on the real path (audit line 210) | partial | batch 7 exemplars, mode=record; A/B not started |
| W10 | 60% of goals target code the writer never runs (audit line 221) | done-flag | batch 9 ETHER_GOAL_LIVE_ONLY=1 |
| W11 | 73% of the codebase is unreachable from the writer (audit line 232) | partial | batch 10 item 1: 44 files / 4,158 lines to attic/ (of 56.6k unreachable); 100+ doubtful modules left in place |
| W12 | Prompt stack is two hard-coded strings (audit line 243) | partial | arm behaviours (batches 2-8); prompt registry open |
| W13 | Live tool surface is 5 toy skills (audit line 254) | partial | batch 9 read-only search/read; batch 10 MCP (item 3) + LSP (item 4) skills, flag-off |
| W14 | Black Tourmaline on the live path is a substring check (audit line 265) | partial | batch 9 ETHER_GEM_PREGATE AST security check, flag-off; batch 10 ETHER_LSP_PREGATE |
| W15 | '8 gems with strongly-typed interfaces' is not what runs (audit line 276) | open |  |
| W16 | Errors are swallowed everywhere (audit line 287) | open |  |
| W17 | Git is used as a telemetry bus (audit line 298) | done | batch 9 |
| W18 | Leftover dashboard has unauthenticated write routes (audit line 309) | done | batch 9 |
| W19 | The Face is stale and blind to learning (audit line 320) | done | batch 9 unison learning view |
| W20 | No external benchmark (audit line 331) | open |  |
| W21 | 74 standing test failures and 83 skips (audit line 342) | open |  |
| W22 | Edits are whole-function rewrites (audit line 353) | partial | batch 6 span edits; batch 5 multi-edit (flag) |
| W23 | No repository map on the real path (audit line 364) | partial | repo_map_on bandit arm |
| W24 | Swarm, LSP, MCP and web connect are mostly aspirational (audit line 375) | partial | batch 10: MCP client+server (item 3), LSP client (item 4), proposer swarm (item 5), all flag-off; web retrieval open |
| W25 | No lifecycle hooks on the writer path (audit line 386) | open |  |
| W26 | No reflection on the real path (audit line 397) | open |  |
| W27 | No planner on the real path (audit line 408) | open |  |
| W28 | No user-facing coding UX (audit line 419) | open |  |
| W29 | ETHER only edits itself (audit line 430) | open |  |
| W30 | No measured position against SOTA (audit line 441) | open |  |
| W31 | Provider layer is raw urllib with no retry or telemetry (audit line 452) | open |  |
| W32 | Each attempt pays two fresh pytest runs (audit line 463) | open |  |
| W33 | Health reports 'running, 0 failures' while nothing works (audit line 474) | done | batch 9 |
| W34 | Writes and reverts are not atomic (audit line 485) | done | batch 9 TreeGuard + FileTx restore |
| W35 | GitHub token on the push URL and in the test environment (audit line 496) | done | batch 9 |
| W36 | Kept code edits auto-push to main with no review (audit line 507) | owner | reviewed host/kept branch: not built |
| W37 | Prompt-injection surface into the tool router (audit line 518) | partial | batch 9 model-callable skills are read-only; no strict envelope |
| W38 | Curriculum filler was written into production modules (audit line 529) | open |  |
| W39 | Lint goals pass on any passing test (audit line 540) | open |  |
| W40 | Two unrelated context knobs and a truncation that can cut the instruction (audit line 551) | open |  |
| W41 | Windows-only learning, hard-coded paths and host identity (audit line 562) | open |  |
| W42 | Evolution pillar never runs on the host (audit line 573) | owner | evolution pillar: retire or rebuild |
| W43 | Several processes can call tick() (audit line 584) | partial | batch 10 model_lock serializes swarm model calls; tick() single-caller not enforced |
| W44 | Six memory stores, none shared (audit line 595) | open |  |
| W45 | Reward ignores cost; arms are near-identical (audit line 606) | partial | kept_per_gpu_hour published; ETHER_BANDIT_COST flag (off) |
| W46 | SBFL points at shared helpers (audit line 617) | partial | batch 3 shared-target try cap; batch 10 cluster re-admission |
| W47 | goal_index.json is read-modify-written without a lock (audit line 628) | partial | atomic os.replace on save; no lock across processes (batch 10 adds abort/rounds fields to the same file) |
| W48 | No structured output (audit line 639) | open |  |
| W49 | ReAct is two turns and tool use is never rewarded (audit line 650) | open |  |
| W50 | Operators read raw JSON on GitHub (audit line 661) | open |  |
| W51 | No overfitting check on kept edits (audit line 672) | open |  |
| W52 | Throughput ceiling and no prefix reuse (audit line 683) | open |  |
| W53 | Docs contradict the code (audit line 694) | partial | batch 9 STATUS/FLAGS/BATCH9 docs; batch 10 BATCH10/AUDIT_TODO |
| W54 | Configuration by 1,188 env flags (audit line 705) | open |  |
| W55 | Lessons are status strings (audit line 716) | open |  |
| W56 | Tool contract is invisible to the model (audit line 727) | partial | batch 10 tool_hint line for mcp/lsp |
| W57 | Error text truncated from the wrong end (audit line 738) | open |  |
| W58 | Search skips scripts/ and gems/ (audit line 749) | open |  |
| W59 | Pre-gate checks stop at compile() (audit line 760) | partial | batch 9 gem pre-gate; batch 10 LSP diagnostics pre-gate + swarm compile screen (flags) |
| W60 | Trajectories cannot be replayed (audit line 771) | open |  |
| W61 | artifacts/ tracked in git (audit line 782) | done | batch 9 |
| W62 | Branch protection and provenance not evident (audit line 793) | open |  |
| W63 | No quality gates before keep (audit line 804) | partial | batch 9 ETHER_GEM_PREGATE AST security check, flag-off; batch 10 ETHER_LSP_PREGATE |
| W64 | No persisted test-to-code map (audit line 815) | open |  |
| W65 | Status theatre misleads the owner (audit line 826) | done | batch 9 |
| W66 | Two learning systems (audit line 837) | open |  |
| W67 | No sandboxed command tool (audit line 848) | partial | batch 10 jail wraps the gate's pytest only; no model-callable command tool (by design) |
| W68 | Mixed reply protocols (audit line 859) | open |  |
| W69 | Feature gap to Claude Code, Aider, OpenHands, SWE-agent (audit line 870) | open |  |
| W70 | GPU idles while pytest runs (audit line 881) | partial | batch 10 swarm: CPU screening overlaps generation (flag-off); pytest/GPU overlap open |
| W71 | Single model, no escalation (audit line 892) | open |  |
| W72 | No real subagents (audit line 903) | partial | batch 10 swarm proposers share one model, no isolated contexts |
| W73 | Sparse 0/1 reward (audit line 914) | open |  |
| W74 | No web or documentation retrieval (audit line 925) | open |  |
| W75 | Token and latency telemetry discarded (audit line 936) | open |  |
| W76 | No model-loaded health probe or circuit breaker (audit line 947) | open |  |
| W77 | Hand-tuned goal ranking (audit line 958) | open |  |
| W78 | Thinking mode hard-disabled (audit line 969) | open |  |
| W79 | Status-theatre tests dominate suite time (audit line 980) | open |  |
| W80 | No per-edit explanation to the owner (audit line 991) | open |  |
| W81 | No caching of parses and reads (audit line 1002) | partial | import graph cached on tree stats |
| W82 | Fixed MAX_TRIES (audit line 1013) | partial | batch 10 item 0: abort backoff, re-admission rounds (ETHER_GOAL_RETRY_S/MAX_ROUNDS); MAX_TRIES still fixed |
| W83 | No post-mortem on reverts (audit line 1024) | open |  |
| W84 | Dual gem naming (audit line 1035) | open |  |
| W85 | Doc sprawl (audit line 1046) | open |  |
| W86 | Memory depends on services that are not running (audit line 1057) | open |  |
| W87 | No checkpoints beyond one revert (audit line 1068) | open |  |
| W88 | Real batch size comes from the retired ladder (audit line 1079) | open |  |
| W89 | Equivalent failures not clustered (audit line 1090) | open |  |
| W90 | Windows scheduled-task sprawl (audit line 1101) | open |  |
| W91 | Self-heal installs persistence every tick (audit line 1112) | open |  |
| W92 | JSON artifacts rewritten every tick (audit line 1123) | open |  |
| W93 | No canary for default flips (audit line 1134) | open |  |
| W94 | Owner policy is a hard-coded tuple (audit line 1145) | open |  |
| W95 | No live attempt progress (audit line 1156) | open |  |
| W96 | No test synthesis on the real path (audit line 1167) | open |  |
| W97 | Ollama host hard-coded (audit line 1178) | open |  |
| W98 | Stash entries accumulate on the writer (audit line 1189) | open |  |
| W99 | RL and MARL studies have no evaluation harness (audit line 1200) | open |  |
| W100 | Spoiler guard false positives burn goals (audit line 1211) | open |  |

Improvements (sec. 6): done 10, done-flag 3, open 70, owner 2, partial 15

## Improvements (sec. 6)

| id | item | status | evidence / batch |
|---|---|---|---|
| I1 | Reconcile the diverged host clone and count pull failures (audit line 1228) | done | batch 9 |
| I2 | Push batch 7 and run first_hour_report at +1 h / +6 h (audit line 1229) | done | batches 2-9 live on origin main |
| I3 | Read-only tool set on the real path + tree-diff gate (audit line 1230) | done | batch 9 |
| I4 | Abort attempt on empty or timed-out baseline (audit line 1231) | done | batch 9 abort; batch 10 item 0: abort no longer burns tries, timeout scales with measured time |
| I5 | Try-indexed temperature + duplicate-reply skip (audit line 1232) | done-flag | batch 8 ETHER_SAMPLE_TEMP + dedup; batch 10 swarm samples K candidates (ETHER_SWARM=1) |
| I6 | Exemplars record now, A/B on at week 1 (audit line 1233) | partial | batch 7 exemplars, mode=record; A/B not started |
| I7 | Health = worst-of signals (audit line 1234) | done | batch 9 |
| I8 | Weight goals by reachability (audit line 1235) | done-flag | batch 9 ETHER_GOAL_LIVE_ONLY=1 |
| I9 | Matrix read model for learning (audit line 1236) | done | batch 9 |
| I10 | Delete dashboard POST routes (audit line 1237) | open |  |
| I11 | Atomic edit/revert with journal (audit line 1238) | partial | batch 9 TreeGuard/FileTx; no journal |
| I12 | Scrub env for test subprocesses; credential helper for push (audit line 1239) | done | batch 9 |
| I13 | Fast pre-gate checks (audit line 1240) | partial | batch 9 gem pre-gate; batch 10 LSP diagnostics pre-gate + swarm compile screen (flags) |
| I14 | Cache baseline per (goal, tree hash) (audit line 1241) | open |  |
| I15 | Run the target test first, stop early (audit line 1242) | open |  |
| I16 | Provider module with retries and telemetry (audit line 1243) | open |  |
| I17 | Structured failure digest (audit line 1244) | open |  |
| I18 | Budget derived from num_ctx; trim middle, never tail (audit line 1245) | open |  |
| I19 | Explicit output contract + one micro-example (audit line 1246) | open |  |
| I20 | Failure-type repair prompts (audit line 1247) | open |  |
| I21 | Store full replies and diffs (audit line 1248) | open |  |
| I22 | Capability truth table generated from code (audit line 1249) | open |  |
| I23 | Untrack artifacts/ except a small published set (audit line 1250) | open |  |
| I24 | Supervisor sole caller of tick() (audit line 1251) | open |  |
| I25 | pre_keep ruff on diff (audit line 1252) | open |  |
| I26 | Ollama structured outputs for tool calls (audit line 1253) | open |  |
| I27 | keep_alive and stable prompt prefix (audit line 1254) | open |  |
| I28 | Thinking-mode arm for hard goals (audit line 1255) | open |  |
| I29 | Fewer, more distinct bandit arms (audit line 1256) | open |  |
| I30 | Kept per GPU-hour as the headline metric (audit line 1257) | partial | kept_per_gpu_hour published; ETHER_BANDIT_COST flag (off) |
| I31 | Daily digest (audit line 1258) | open |  |
| I32 | Decide the evolution pillar (audit line 1259) | owner | evolution pillar: retire or rebuild |
| I33 | Relabel or wire gems (audit line 1260) | open |  |
| I34 | Branch protection for code paths (audit line 1261) | open |  |
| I35 | Strict tool envelope against injection (audit line 1262) | partial | batch 9 model-callable skills are read-only; no strict envelope |
| I36 | Persist SBFL coverage map (audit line 1263) | open |  |
| I37 | Kept-rate canary dashboard for each batch (audit line 1264) | open |  |
| I38 | Transitive affected-test selection (audit line 1265) | done | batch 9 |
| I39 | Planted-bug goal generator (audit line 1266) | done-flag | batch 9 planted goals (ETHER_PLANTED_GOALS=1); batch 10 item 0 re-admits exhausted goals |
| I40 | Per-attempt disposable worktree (audit line 1267) | open |  |
| I41 | Nightly micro-benchmark (SWE-style + held-out planted bugs) (audit line 1268) | open |  |
| I42 | Kept edits to host/kept branch; nightly full suite fast-forwards main (audit line 1269) | owner | reviewed host/kept branch: not built |
| I43 | Nightly full-suite sweep with blame and auto-revert (audit line 1270) | open |  |
| I44 | Windows Job Object sandbox, no network (audit line 1271) | partial | batch 10 item 2 Job Object (memory/process/CPU caps, kill-on-close); no-network rule is an optional admin script |
| I45 | ACI-style read-only tools (audit line 1272) | partial | batch 9 read-only search/read; batch 10 MCP (item 3) + LSP (item 4) skills, flag-off |
| I46 | Search/replace edit format arm (audit line 1273) | open |  |
| I47 | Ranked repo map arm (audit line 1274) | partial | repo_map_on bandit arm |
| I48 | Versioned prompt registry (audit line 1275) | open |  |
| I49 | Structured reflection step (audit line 1276) | open |  |
| I50 | One episodic store (SQLite) (audit line 1277) | open |  |
| I51 | Telemetry off main (audit line 1278) | done | batch 9 |
| I52 | Typed error taxonomy with escalation (audit line 1279) | open |  |
| I53 | Linux 'sim host' for CI (audit line 1280) | open |  |
| I54 | Task intake for the owner (audit line 1281) | open |  |
| I55 | Owner policy file (audit line 1282) | open |  |
| I56 | Advertise tool schema in investigation prompts (audit line 1283) | partial | batch 10 tool_hint line for mcp/lsp |
| I57 | Single reply protocol per turn type (audit line 1284) | open |  |
| I58 | Reply caps by goal kind (audit line 1285) | done | batch 4 reply cap follows target size |
| I59 | Model-loaded probe and circuit breaker (audit line 1286) | open |  |
| I60 | Posterior-based stopping per goal (audit line 1287) | open |  |
| I61 | Failure clustering (audit line 1288) | open |  |
| I62 | Revert taxonomy -> retargeting (audit line 1289) | open |  |
| I63 | Attempt event log the Matrix tails (audit line 1290) | open |  |
| I64 | Meaningful commit messages (audit line 1291) | open |  |
| I65 | Generated STATUS.md; prune docs (audit line 1292) | open |  |
| I66 | Remove status-theatre modules and tests (audit line 1293) | partial | batch 10 item 1: 44 files / 4,158 lines to attic/ (of 56.6k unreachable); 100+ doubtful modules left in place |
| I67 | Unify arm behaviour definitions (audit line 1294) | open |  |
| I68 | Self-heal installs once (audit line 1295) | open |  |
| I69 | One Windows task (audit line 1296) | open |  |
| I70 | Atomic, versioned goal index (audit line 1297) | partial | atomic os.replace on save; no lock across processes (batch 10 adds abort/rounds fields to the same file) |
| I71 | Lint keep needs module tests (audit line 1298) | open |  |
| I72 | Whole-repo search (audit line 1299) | open |  |
| I73 | Default flips ship as bandit arms first (audit line 1300) | open |  |
| I74 | Remove remaining filler functions (audit line 1301) | open |  |
| I75 | Owner-approved notification hook (audit line 1302) | open |  |
| I76 | Agentless-style localize-repair-select planner (audit line 1303) | open |  |
| I77 | Exception-origin anchoring for SBFL (audit line 1304) | open |  |
| I78 | Typed configuration (audit line 1305) | open |  |
| I79 | Triage the 74 failing tests (audit line 1306) | open |  |
| I80 | Aider baseline on the same model (audit line 1307) | open |  |
| I81 | Hidden asserts and literal-branch rejection (audit line 1308) | open |  |
| I82 | Lifecycle hooks (audit line 1309) | open |  |
| I83 | AST security policy on diffs (audit line 1310) | partial | batch 9 ETHER_GEM_PREGATE AST security check, flag-off; batch 10 ETHER_LSP_PREGATE |
| I84 | Investigation turns with capped reads (audit line 1311) | open |  |
| I85 | Learning-progress curriculum (audit line 1312) | open |  |
| I86 | ExpeL-style insight rules (audit line 1313) | open |  |
| I87 | Diff summary + approval for owner tasks (audit line 1314) | open |  |
| I88 | CPU-side workers under the supervisor (audit line 1315) | partial | batch 10 swarm: CPU screening overlaps generation (flag-off); pytest/GPU overlap open |
| I89 | Offline replay environment (audit line 1316) | open |  |
| I90 | Strangler deletion of unreachable modules (audit line 1317) | partial | batch 10 item 1: 44 files / 4,158 lines to attic/ (of 56.6k unreachable); 100+ doubtful modules left in place |
| I91 | Pipeline generation with gating (audit line 1318) | open |  |
| I92 | Workspace abstraction for external repos (audit line 1319) | open |  |
| I93 | Test synthesis from issues (audit line 1320) | open |  |
| I94 | Optional CPU-offloaded larger model for a nightly hard batch (audit line 1321) | open |  |
| I95 | Offline doc cache (audit line 1322) | open |  |
| I96 | Write artifacts on change only (audit line 1323) | open |  |
| I97 | Qualified-name spoiler guard (audit line 1324) | open |  |
| I98 | Memoise parses (audit line 1325) | partial | import graph cached on tree stats |
| I99 | Rebase --autostash instead of manual stash (audit line 1326) | open |  |
| I100 | Respect OLLAMA_HOST (audit line 1327) | open |  |

Missing features (sec. 7): done 1, done-flag 4, open 33, partial 12

## Missing features (sec. 7)

| id | item | status | evidence / batch |
|---|---|---|---|
| F1 | Sandboxed execution runtime for every attempt (audit line 1333) | partial | batch 9 mirror + scrubbed env; batch 10 item 2 OS jail (bwrap/unshare/rlimits, Windows Job Object); no network block on Windows |
| F2 | Repeated sampling + test-based selection (audit line 1334) | partial | batch 10 swarm: K samples, static screen, best one gated; no test-based ranking among candidates |
| F3 | Episodic memory of solved tasks (audit line 1335) | partial | batch 7 exemplars, mode=record; A/B not started |
| F4 | Automatic task generation (audit line 1336) | done-flag | batch 9 planted goals (ETHER_PLANTED_GOALS=1); batch 10 item 0 re-admits exhausted goals |
| F5 | Secret scrubbing for tool subprocesses (audit line 1337) | done | batch 9 |
| F6 | Prompt-injection defences for tool calls (audit line 1338) | partial | batch 9 model-callable skills are read-only; no strict envelope |
| F7 | Capability truth table (audit line 1339) | open |  |
| F8 | Crash-safe atomic edits (audit line 1340) | partial | batch 9 TreeGuard/FileTx; no journal |
| F9 | Read-only investigation tools (grep, outline, read range) (audit line 1341) | partial | batch 9 read-only search/read; batch 10 MCP (item 3) + LSP (item 4) skills, flag-off |
| F10 | Search/replace or diff edit format (audit line 1342) | partial | batch 6 span edits; batch 5 multi-edit (flag) |
| F11 | Ranked repository map (audit line 1343) | partial | repo_map_on bandit arm |
| F12 | Run a single test or command during investigation (audit line 1344) | open |  |
| F13 | Git-aware workflow (branch per task, PR) (audit line 1345) | open |  |
| F14 | Linter/formatter in the edit loop (audit line 1346) | open |  |
| F15 | External benchmark harness (audit line 1347) | open |  |
| F16 | Cost/latency telemetry per call (audit line 1348) | partial | secs_per_pull in bandit summary; no token telemetry |
| F17 | Unified episodic store and replay (audit line 1349) | open |  |
| F18 | Lifecycle hooks (audit line 1350) | open |  |
| F19 | Project memory file (conventions) (audit line 1351) | open |  |
| F20 | Structured outputs / tool-call schema (audit line 1352) | open |  |
| F21 | Checkpoints / undo (audit line 1353) | open |  |
| F22 | Typed configuration (audit line 1354) | open |  |
| F23 | Policy / permission file (audit line 1355) | open |  |
| F24 | Held-out tests against overfitting (audit line 1356) | open |  |
| F25 | Prefix/KV cache reuse (audit line 1357) | open |  |
| F26 | Parallel candidate generation (audit line 1358) | partial | batch 10 swarm: K samples, static screen, best one gated; no test-based ranking among candidates |
| F27 | Multi-file edits by default (audit line 1359) | done-flag | batch 5 ETHER_MULTI_EDIT=1 |
| F28 | Planning with explicit task list (audit line 1360) | open |  |
| F29 | Reflection / self-critique between tries (audit line 1361) | open |  |
| F30 | Fault localisation beyond SBFL (audit line 1362) | open |  |
| F31 | Prompt optimisation from outcomes (audit line 1363) | open |  |
| F32 | Human approval / permission modes (audit line 1364) | open |  |
| F33 | Interactive chat UX on the live agent (audit line 1365) | open |  |
| F34 | Skill library of verified procedures (audit line 1366) | open |  |
| F35 | Daily learning report (audit line 1367) | open |  |
| F36 | LSP diagnostics and go-to-definition (audit line 1368) | done-flag | batch 10 item 4 ETHER_LSP=1 (diagnostics, definition, references) |
| F37 | Issue-to-patch intake (audit line 1369) | open |  |
| F38 | Work on external repositories (audit line 1370) | open |  |
| F39 | Self-improvement archive with holdout (audit line 1371) | open |  |
| F40 | Context compaction / summarisation (audit line 1372) | open |  |
| F41 | Model routing by difficulty (audit line 1373) | open |  |
| F42 | Type checker in the loop (audit line 1374) | partial | batch 10 LSP diagnostics (pyright/pylsp if installed); no type-check gate |
| F43 | Streaming progress (audit line 1375) | open |  |
| F44 | Notifications (audit line 1376) | open |  |
| F45 | Subagents with isolated context (audit line 1377) | partial | batch 10 swarm proposers share one model, no isolated contexts |
| F46 | MCP tool consumption in the loop (audit line 1378) | done-flag | batch 10 item 3 ETHER_MCP=1 (read-only) |
| F47 | Web or documentation retrieval (audit line 1379) | open |  |
| F48 | Test generation for issues (audit line 1380) | open |  |
| F49 | Background agents with branch output (audit line 1381) | open |  |
| F50 | Multi-language support (audit line 1382) | open |  |

Architecture (sec. 8): done 1, open 21, owner 1, partial 2

## Architecture (sec. 8)

| id | item | status | evidence / batch |
|---|---|---|---|
| A1 | Writer kernel split: tick = perceive / select / attempt / keep / publish (audit line 1386) | open |  |
| A2 | Attempt runs in a disposable worktree (audit line 1387) | open |  |
| A3 | Kept edits flow through host/kept, main via nightly full suite (audit line 1388) | owner | reviewed host/kept branch: not built |
| A4 | Telemetry channel separate from code history (audit line 1389) | done | batch 9 |
| A5 | One episodic store (SQLite, WAL) (audit line 1390) | open |  |
| A6 | Single provider module (audit line 1391) | open |  |
| A7 | Strangler: live allowlist + legacy/ package (audit line 1392) | open |  |
| A8 | Typed configuration object (audit line 1393) | open |  |
| A9 | Goal source as a plug-in interface (audit line 1394) | open |  |
| A10 | Gate as a first-class component (audit line 1395) | partial | gate in goal_source.gate + sandbox/jail; gems as flag-off pre-gate |
| A11 | Policy engine (hooks + permissions) (audit line 1396) | open |  |
| A12 | Tool layer with schemas and permissions (audit line 1397) | open |  |
| A13 | Capability registry drives docs and Matrix (audit line 1398) | open |  |
| A14 | Matrix read model v2 (audit line 1399) | open |  |
| A15 | Supervisor owns scheduling of CPU workers (audit line 1400) | open |  |
| A16 | Error taxonomy and health model (audit line 1401) | open |  |
| A17 | Sim host for Linux CI (audit line 1402) | open |  |
| A18 | Workspace abstraction (audit line 1403) | open |  |
| A19 | Learning layer boundary (audit line 1404) | open |  |
| A20 | Gems as optional, measured stages (audit line 1405) | partial | gate in goal_source.gate + sandbox/jail; gems as flag-off pre-gate |
| A21 | Planner component (audit line 1406) | open |  |
| A22 | Replay environment (audit line 1407) | open |  |
| A23 | Evolution with an honest gate (audit line 1408) | open |  |
| A24 | Archive of agent variants (data-level) (audit line 1409) | open |  |
| A25 | Single entry point and lock (audit line 1410) | open |  |

Prompts (sec. 9): done 1, open 24

## Prompts (sec. 9)

| id | item | status | evidence / batch |
|---|---|---|---|
| P1 | EDIT system prompt with an explicit output contract (audit line 1414) | open |  |
| P2 | Goal header that states the failure precisely (audit line 1434) | open |  |
| P3 | Retry prompt by failure type: assertion delta (audit line 1450) | open |  |
| P4 | Retry prompt by failure type: regression (audit line 1459) | open |  |
| P5 | Retry prompt by failure type: no extractable code (audit line 1468) | open |  |
| P6 | Span window prompt (audit line 1475) | done | batch 6 span window prompt |
| P7 | Investigation turn prompt with tool schema (audit line 1483) | open |  |
| P8 | Exemplar block wording (audit line 1492) | open |  |
| P9 | Reflection micro-prompt (audit line 1501) | open |  |
| P10 | Assignment goal prompt (audit line 1508) | open |  |
| P11 | Lint goal prompt (audit line 1515) | open |  |
| P12 | Project conventions block (from ETHER.md, 300 chars) (audit line 1522) | open |  |
| P13 | Remove READ protocol from the live system prompt (audit line 1523) | open |  |
| P14 | Planner prompt (localisation) (audit line 1524) | open |  |
| P15 | Candidate selection prompt (optional) (audit line 1531) | open |  |
| P16 | Structured output for tool turns (audit line 1538) | open |  |
| P17 | Keep prompts deterministic in prefix (audit line 1539) | open |  |
| P18 | Version every prompt (audit line 1540) | open |  |
| P19 | Negative instructions trimmed (audit line 1541) | open |  |
| P20 | Test source framing (audit line 1542) | open |  |
| P21 | Error digest instead of raw tail (audit line 1543) | open |  |
| P22 | Hard-goal thinking arm prompt (audit line 1544) | open |  |
| P23 | Temperature-aware diversity cue (audit line 1545) | open |  |
| P24 | Owner task prompt (audit line 1546) | open |  |
| P25 | Prompt A/B guard (audit line 1547) | open |  |

Context (sec. 10): done 1, open 22, partial 2

## Context (sec. 10)

| id | item | status | evidence / batch |
|---|---|---|---|
| C1 | Budget from num_ctx (audit line 1553) | done | context_char_budget from ETHER_MODEL_CTX (batch 2 test) |
| C2 | Section priority packing (audit line 1554) | open |  |
| C3 | Never cut the tail (audit line 1555) | open |  |
| C4 | Structured failure digest (audit line 1556) | open |  |
| C5 | Ranked repo map (audit line 1557) | partial | repo_map_on bandit arm |
| C6 | Callee/caller slice (audit line 1558) | open |  |
| C7 | Constant slice (audit line 1559) | open |  |
| C8 | Test fixture inclusion (audit line 1560) | open |  |
| C9 | Exemplar retrieval (audit line 1561) | partial | batch 7 exemplars, mode=record; A/B not started |
| C10 | Context source as bandit arm (audit line 1562) | open |  |
| C11 | Measured chars/token (audit line 1563) | open |  |
| C12 | KV-prefix stable ordering (audit line 1564) | open |  |
| C13 | Per-goal context cache (audit line 1565) | open |  |
| C14 | Window shrink policy for spans (audit line 1566) | open |  |
| C15 | Project conventions snippet (audit line 1567) | open |  |
| C16 | Context provenance logging (audit line 1568) | open |  |
| C17 | Spoiler and leak guard on all sections (audit line 1569) | open |  |
| C18 | Compression of long tests (audit line 1570) | open |  |
| C19 | Diff-aware context on retries (audit line 1571) | open |  |
| C20 | Coverage-guided line focus (audit line 1572) | open |  |
| C21 | Owner-task context (audit line 1573) | open |  |
| C22 | Context budget telemetry on the Matrix (audit line 1574) | open |  |
| C23 | Overflow alarms (audit line 1575) | open |  |
| C24 | Memory hygiene (audit line 1576) | open |  |
| C25 | 8K context experiment (audit line 1577) | open |  |

Planner (sec. 11): done-flag 3, open 20, partial 2

## Planner (sec. 11)

| id | item | status | evidence / batch |
|---|---|---|---|
| PL1 | Hierarchical localisation (Agentless) (audit line 1581) | open |  |
| PL2 | Hypothesis list per goal (audit line 1582) | open |  |
| PL3 | Candidate generation + test selection (audit line 1583) | partial | batch 10 swarm: K samples, static screen, best one gated; no test-based ranking among candidates |
| PL4 | Duplicate-AST pruning (audit line 1584) | open |  |
| PL5 | Posterior stopping rule (audit line 1585) | open |  |
| PL6 | Learning-progress curriculum (audit line 1586) | open |  |
| PL7 | Reachability-weighted ranking (audit line 1587) | done-flag | batch 9 ETHER_GOAL_LIVE_ONLY=1 |
| PL8 | Failure clustering (audit line 1588) | open |  |
| PL9 | Planted-bug generator (audit line 1589) | done-flag | batch 9 planted goals (ETHER_PLANTED_GOALS=1); batch 10 item 0 re-admits exhausted goals |
| PL10 | Difficulty ladder from planted bugs (audit line 1590) | open |  |
| PL11 | Multi-site plans (audit line 1591) | done-flag | batch 5 ETHER_MULTI_EDIT=1 |
| PL12 | Retarget after wrong-target reverts (audit line 1592) | open |  |
| PL13 | Plan as data (audit line 1593) | open |  |
| PL14 | Budget-aware scheduling (audit line 1594) | open |  |
| PL15 | Hierarchical bandit (pipeline -> prompt) (audit line 1595) | open |  |
| PL16 | Contextual features for arm choice (audit line 1596) | partial | bandit buckets by goal class (gen|complex, repair_logic|complex) |
| PL17 | Owner tasks priority lane (audit line 1597) | open |  |
| PL18 | Goal value from downstream use (audit line 1598) | open |  |
| PL19 | Reflection-gated retries (audit line 1599) | open |  |
| PL20 | Thinking budget for hard goals (audit line 1600) | open |  |
| PL21 | Nightly hard batch (audit line 1601) | open |  |
| PL22 | Hold-out discipline (audit line 1602) | open |  |
| PL23 | Plan quality metric (audit line 1603) | open |  |
| PL24 | Coverage-gap goals (audit line 1604) | open |  |
| PL25 | Offline policy evaluation before rollout (audit line 1605) | open |  |

Tools (sec. 12): done 2, done-flag 4, open 17, partial 2

## Tools (sec. 12)

| id | item | status | evidence / batch |
|---|---|---|---|
| T1 | grep (audit line 1609) | partial | search skill (core/ + tests/) |
| T2 | outline (audit line 1610) | open |  |
| T3 | read (audit line 1611) | done | batch 9 |
| T4 | find_symbol (audit line 1612) | done-flag | batch 10 LSP definition |
| T5 | references (audit line 1613) | done-flag | batch 10 item 4 ETHER_LSP=1 (diagnostics, definition, references) |
| T6 | run_test (audit line 1614) | open |  |
| T7 | show_diff (audit line 1615) | open |  |
| T8 | edit tool removal (audit line 1616) | done | batch 9 |
| T9 | Tool schema registry (audit line 1617) | open |  |
| T10 | Strict envelope (audit line 1618) | open |  |
| T11 | Output caps and truncation markers (audit line 1619) | open |  |
| T12 | Tool telemetry (audit line 1620) | open |  |
| T13 | Tool-use bandit arm (audit line 1621) | open |  |
| T14 | Lint tool (audit line 1622) | open |  |
| T15 | Type check tool (later) (audit line 1623) | open |  |
| T16 | Coverage tool (audit line 1624) | open |  |
| T17 | Git tools (read-only) (audit line 1625) | open |  |
| T18 | Doc lookup (audit line 1626) | open |  |
| T19 | MCP bridge (read-only first) (audit line 1627) | done-flag | batch 10 item 3 ETHER_MCP=1 (read-only) |
| T20 | LSP bridge (audit line 1628) | done-flag | batch 10 item 4 ETHER_LSP=1 (diagnostics, definition, references) |
| T21 | Sandbox runner (audit line 1629) | partial | batch 9 mirror + scrubbed env; batch 10 item 2 OS jail (bwrap/unshare/rlimits, Windows Job Object); no network block on Windows |
| T22 | Rate and budget limits (audit line 1630) | open |  |
| T23 | Deterministic tool outputs (audit line 1631) | open |  |
| T24 | Tool fabrication only via evolution gate (audit line 1632) | open |  |
| T25 | Tool docs generated (audit line 1633) | open |  |

Reliability (sec. 13): done 3, open 19, partial 3

## Reliability (sec. 13)

| id | item | status | evidence / batch |
|---|---|---|---|
| R1 | Pull divergence (audit line 1637) | done | batch 9 |
| R2 | Health model (audit line 1638) | done | batch 9 |
| R3 | Swallowed exceptions (audit line 1639) | open |  |
| R4 | Baseline timeout (audit line 1640) | done | batch 9 abort; batch 10 item 0: abort no longer burns tries, timeout scales with measured time |
| R5 | Atomic writes (audit line 1641) | partial | batch 9 TreeGuard/FileTx; no journal |
| R6 | Worktree attempts (audit line 1642) | open |  |
| R7 | Post-pull smoke and rollback (audit line 1643) | open |  |
| R8 | Selfcheck of lazy imports (audit line 1644) | open |  |
| R9 | Model probe and breaker (audit line 1645) | open |  |
| R10 | Provider retries (audit line 1646) | open |  |
| R11 | Disk and repo size guard (audit line 1647) | open |  |
| R12 | Lock robustness (audit line 1648) | partial | batch 10 model_lock serializes swarm model calls; tick() single-caller not enforced |
| R13 | Goal index integrity (audit line 1649) | partial | atomic os.replace on save; no lock across processes (batch 10 adds abort/rounds fields to the same file) |
| R14 | Nightly full suite with blame (audit line 1650) | open |  |
| R15 | Main protection (audit line 1651) | open |  |
| R16 | Linux sim host CI (audit line 1652) | open |  |
| R17 | Green test baseline (audit line 1653) | open |  |
| R18 | Error budget and SLOs (audit line 1654) | open |  |
| R19 | Supervisor backoff (audit line 1655) | open |  |
| R20 | Ollama VRAM pressure (audit line 1656) | open |  |
| R21 | Clock and timezone hygiene (audit line 1657) | open |  |
| R22 | Idempotent ticks (audit line 1658) | open |  |
| R23 | Windows task sprawl (audit line 1659) | open |  |
| R24 | Chaos tests (audit line 1660) | open |  |
| R25 | Runbook generated from health states (audit line 1661) | open |  |

UX (sec. 14): done 2, open 20, partial 3

## UX (sec. 14)

| id | item | status | evidence / batch |
|---|---|---|---|
| U1 | Matrix learning panel (audit line 1665) | done | batch 9 |
| U2 | Health light (audit line 1666) | done | batch 9 |
| U3 | Capability truth table (audit line 1667) | open |  |
| U4 | Daily digest (audit line 1668) | open |  |
| U5 | Owner task intake (audit line 1669) | open |  |
| U6 | Diff review before merge (audit line 1670) | open |  |
| U7 | Readable commit messages (audit line 1671) | open |  |
| U8 | first_hour_report in the Matrix (audit line 1672) | partial | scripts/first_hour_report.py |
| U9 | Attempt timeline (audit line 1673) | open |  |
| U10 | Notifications via owner-approved channel (audit line 1674) | open |  |
| U11 | Generated STATUS.md (audit line 1675) | open |  |
| U12 | Doc pruning (audit line 1676) | open |  |
| U13 | Flag catalogue (audit line 1677) | partial | batch 9 STATUS/FLAGS/BATCH9 docs; batch 10 BATCH10/AUDIT_TODO |
| U14 | Batch report template (audit line 1678) | partial | batch 9 STATUS/FLAGS/BATCH9 docs; batch 10 BATCH10/AUDIT_TODO |
| U15 | Goal browser (audit line 1679) | open |  |
| U16 | Arm explanations (audit line 1680) | open |  |
| U17 | Kept-edit gallery (audit line 1681) | open |  |
| U18 | Revert reasons chart (audit line 1682) | open |  |
| U19 | Owner policy editor (file) (audit line 1683) | open |  |
| U20 | CLI parity (audit line 1684) | open |  |
| U21 | Weekly benchmark trend (audit line 1685) | open |  |
| U22 | Clear error messages (audit line 1686) | open |  |
| U23 | Time zone display (audit line 1687) | open |  |
| U24 | Approval mode for risky edits (audit line 1688) | open |  |
| U25 | Onboarding script (audit line 1689) | open |  |

Performance (sec. 15): done 3, done-flag 1, open 16, partial 5

## Performance (sec. 15)

| id | item | status | evidence / batch |
|---|---|---|---|
| PF1 | Baseline cache (audit line 1693) | open |  |
| PF2 | Target-first gate (audit line 1694) | open |  |
| PF3 | Pre-gate lint/import (audit line 1695) | partial | batch 9 gem pre-gate; batch 10 LSP diagnostics pre-gate + swarm compile screen (flags) |
| PF4 | Duplicate skip (audit line 1696) | done-flag | batch 8 duplicate-reply skip |
| PF5 | keep_alive (audit line 1697) | open |  |
| PF6 | Stable prefix ordering (audit line 1698) | open |  |
| PF7 | Reply caps by kind (audit line 1699) | done | batch 4 reply cap follows target size |
| PF8 | Pipeline generate-while-gating (audit line 1700) | partial | batch 10 swarm: CPU screening overlaps generation (flag-off); pytest/GPU overlap open |
| PF9 | Warm pytest worker (audit line 1701) | open |  |
| PF10 | Transitive selection with time budget (audit line 1702) | partial | batch 10 item 0: gate timeout scales with measured secs/file; per-goal trimming after aborts |
| PF11 | Bytecode drop scope (audit line 1703) | done | bytecode drop window |
| PF12 | Telemetry off main (audit line 1704) | done | batch 9 |
| PF13 | Write-on-change artifacts (audit line 1705) | open |  |
| PF14 | Parse/read memoisation (audit line 1706) | open |  |
| PF15 | Suite pruning (status theatre) (audit line 1707) | partial | batch 10 item 1: 44 files / 4,158 lines to attic/ (of 56.6k unreachable); 100+ doubtful modules left in place |
| PF16 | Token telemetry (audit line 1708) | open |  |
| PF17 | Context size arm (4K vs 8K) (audit line 1709) | open |  |
| PF18 | Quantisation check (audit line 1710) | open |  |
| PF19 | Thinking arm cost (audit line 1711) | open |  |
| PF20 | CPU worker offload (audit line 1712) | partial | batch 10 swarm: CPU screening overlaps generation (flag-off); pytest/GPU overlap open |
| PF21 | SBFL scan scheduling (audit line 1713) | open |  |
| PF22 | Nightly full suite (audit line 1714) | open |  |
| PF23 | Benchmark harness (audit line 1715) | open |  |
| PF24 | Latency SLO (audit line 1716) | open |  |
| PF25 | Perf regression gate (audit line 1717) | open |  |

Moonshots (sec. 16): done-flag 1, open 24

## Moonshots (sec. 16)

| id | item | status | evidence / batch |
|---|---|---|---|
| M1 | Self-play bug planting and fixing (SWE-smith on itself) (audit line 1723) | done-flag | batch 9 planted goals (ETHER_PLANTED_GOALS=1); batch 10 item 0 re-admits exhausted goals |
| M2 | Overnight local distillation (audit line 1724) | open |  |
| M3 | MAP-Elites archive of prompts and pipelines (audit line 1725) | open |  |
| M4 | GEPA-style reflective prompt evolution (audit line 1726) | open |  |
| M5 | Darwin-Gödel-style variant archive (data-level only) (audit line 1727) | open |  |
| M6 | Verified skill library (audit line 1728) | open |  |
| M7 | Test-time search with a learned verifier (audit line 1729) | open |  |
| M8 | Causal fault localisation (audit line 1730) | open |  |
| M9 | Speculative decoding with a 0.5B draft (audit line 1731) | open |  |
| M10 | Continuous property-based testing (audit line 1732) | open |  |
| M11 | Cross-repo transfer (audit line 1733) | open |  |
| M12 | Owner-intent model (audit line 1734) | open |  |
| M13 | Self-documenting architecture (audit line 1735) | open |  |
| M14 | Formal contracts on the writer path (audit line 1736) | open |  |
| M15 | Energy-aware scheduling (audit line 1737) | open |  |
| M16 | Multi-host swarm (opt-in) (audit line 1738) | open |  |
| M17 | Semantic diff memory (audit line 1739) | open |  |
| M18 | Counterfactual replay for OPE (audit line 1740) | open |  |
| M19 | Curriculum from upstream projects (audit line 1741) | open |  |
| M20 | Automatic test hardening (audit line 1742) | open |  |
| M21 | Agentic code review gem (audit line 1743) | open |  |
| M22 | Natural-language owner console (audit line 1744) | open |  |
| M23 | Learned guard-suite selection (audit line 1745) | open |  |
| M24 | Hardware-adaptive model choice (audit line 1746) | open |  |
| M25 | Living roadmap (audit line 1747) | open |  |

Owner decisions (sec. 19): owner 5, partial 1

## Owner decisions (sec. 19)

| id | item | status | evidence / batch |
|---|---|---|---|
| D1 | Agent swarm: CPU workers that never write (doctrine-compatible) vs a GPU multi-agent swarm (doctrine change, n (audit line 1894) | owner | batch 10 built the doctrine-compatible reading (one model, serialized calls, CPU screens, one writer), ETHER_SWARM default off; default-on is the owner's call |
| D2 | Kept code edits go to `host/kept` and reach `main` only after a nightly full suite (keeps single writer; chang (audit line 1895) | owner | reviewed host/kept branch: not built |
| D3 | Delete vs quarantine the 73% unreachable code. (audit line 1896) | partial | batch 10 item 1: 44 files / 4,158 lines to attic/ (of 56.6k unreachable); 100+ doubtful modules left in place |
| D4 | Retire or rebuild the evolution pillar with an honest gate. (audit line 1897) | owner | evolution pillar: retire or rebuild |
| D5 | Off-host distillation / any second machine (doctrine change). (audit line 1898) | owner | not started |
| D6 | Thinking mode and 8K context as bandit arms on the 1650 (within doctrine; VRAM risk). (audit line 1899) | owner | not started |
