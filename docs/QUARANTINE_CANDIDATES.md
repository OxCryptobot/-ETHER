# Quarantine candidates (batch 9, read-only list — nothing was moved or deleted)

Owner decision pending (audit W11): dead code is **not** deleted in batch 9. This list is generated from
static import reachability from `scripts/host_main.py` and `scripts/host_supervisor.py` (lazy imports count;
re-exports in package `__init__` files are not followed, because importing anything under `core/` executes
`core/__init__.py`, which imports the legacy pipeline the writer never calls). Regenerate with
`core.agent.planted.live_files`. A file listed here may still be used by tests, the CLI or the Matrix tooling;
check before moving anything.

- Live (reachable) modules: **145**, 25,929 lines.
- Not reachable: **413** modules, 59,491 lines.
- Seed goals (`config/goal_seed.json`, fix_test) on unreachable files: **35** of 56. `ETHER_GOAL_LIVE_ONLY=1` skips them.

Suggested strangler order (owner to approve): 1) freeze this list; 2) move to `legacy/` with their tests;
3) delete after two weeks with no import from the writer or the CLI.

| Directory | Modules | Lines | Seed goals | Files |
|---|---|---|---|---|
| `scripts` | 86 | 24,877 | 6 | _cq_multifile_snip.py, _obs_snippet.py, _parse_snippet.py, ablation.py, archive_failed.py, archive_script_graveyard.py, assemble_phaseg.py, bandit_sim.py, batch_measure.py, batch_phase_d.py, batch_phase_e.py, batch_phase_f.py, … (+74) |
| `core` | 127 | 18,447 | 21 | __init__.py, __version__.py, agent_loop.py, ast_edit_kpi.py, atomic_rates.py, auto_rate_climb.py, autonomy.py, batch_queue.py, bench_guardian.py, build_progress.py, burst_policy.py, chat_bridge.py, … (+115) |
| `core/loop` | 48 | 3,126 | 4 | __init__.py, agent_loop_path.py, agentic.py, ast_intel.py, bandit_credit.py, begin.py, canned_tools.py, close_run.py, coord.py, execute_plan.py, extend_stage.py, fail_run.py, … (+36) |
| `dashboard` | 8 | 2,299 | 0 | __init__.py, app.py, collector.py, collector_batch.py, collector_health.py, collector_host_agent.py, collector_moonshots.py, live_feed.py |
| `tools/audit` | 7 | 1,551 | 0 | __init__.py, alerts.py, audit_runner.py, fingerprint.py, fp_feedback.py, ingest.py, regression_tracker.py |
| `tools/audit/rules` | 7 | 1,408 | 0 | __init__.py, arch_boundaries.py, error_handling.py, measurement_integrity.py, perf_contracts.py, security_assumptions.py, state_integrity.py |
| `scripts/_graveyard` | 13 | 1,359 | 0 | apply_clearquartz_import_fix.py, apply_findings_phase_d.py, apply_findings_phase_e.py, apply_ledger_nudge.py, apply_parse_fix.py, apply_phasec_slice3.py, apply_phased_slice1.py, apply_phased_slice1b.py, apply_phased_slice1b_filescope.py, apply_phased_slice1b_fix.py, apply_phased_slice1b_same_workspace.py, apply_phased_slice1b_shortcircuit.py, … (+1) |
| `tools/persistent` | 29 | 1,063 | 0 | apply_patch.py, assert_harness.py, bandit_report.py, complexity_score.py, diff_summary.py, docker_probe.py, failure_cluster.py, few_shot_pack.py, find_symbol.py, generate_tests_stub.py, import_allowlist.py, objective_normalize.py, … (+17) |
| `cli` | 6 | 830 | 0 | __init__.py, commands_batch.py, commands_health.py, commands_learn.py, helpers.py, main.py |
| `core/kernel` | 26 | 814 | 0 | __init__.py, agent.py, autonomy.py, briefing.py, cancel.py, contract.py, crash.py, dirty.py, events.py, gc.py, hooks.py, ignore.py, … (+14) |
| `core/loop/handlers` | 4 | 511 | 4 | __init__.py, finalize.py, tool_runtime_gate.py, verify.py |
| `docs/results/batch5` | 5 | 486 | 0 | goalable5.py, publish_sim.py, replay5.py, sbfl_bench5.py, seed5.py |
| `docs/results/batch6` | 4 | 412 | 0 | gem_mutation6.py, goalable6.py, seed6.py, topology6.py |
| `scripts/_graveyard/host_legacy` | 2 | 384 | 0 | ether_host.py, host_tick.py |
| `core/agent` | 1 | 294 | 0 | runtime.py |
| `docs/results/batch4` | 3 | 239 | 0 | sbfl_bench.py, seed4.py, sim_table.py |
| `gems/citrine` | 2 | 183 | 0 | __init__.py, mcp_server.py |
| `gems/clear_quartz` | 2 | 171 | 0 | __init__.py, mcp_server.py |
| `docs/results/batch3` | 4 | 140 | 0 | budget3.py, coverage_live.py, replay3.py, seed3.py |
| `gems/labradorite` | 2 | 115 | 0 | __init__.py, mcp_server.py |
| `tools` | 1 | 106 | 0 | _lib.py |
| `docs/results/batch7` | 1 | 102 | 0 | exemplar_replay.py |
| `fixtures/repo_oracle_ledger` | 2 | 61 | 0 | account.py, ledger.py |
| `gems/selenite` | 2 | 57 | 0 | __init__.py, langgraph_skeleton.py |
| `patches` | 1 | 53 | 0 | apply_pipeline_81.py |
| `fixtures/_fixed_solutions/ledger` | 2 | 52 | 0 | account.py, ledger.py |
| `fixtures/repo_oracle_merge` | 1 | 41 | 0 | merge.py |
| `fixtures/repo_oracle_topo` | 1 | 39 | 0 | topo.py |
| `fixtures/repo_oracle_lru` | 1 | 32 | 0 | lru.py |
| `fixtures/_fixed_solutions/topo` | 1 | 30 | 0 | topo.py |
| `gems` | 2 | 29 | 0 | __init__.py, runtime.py |
| `fixtures/repo_oracle_intervals` | 1 | 27 | 0 | intervals.py |
| `fixtures/_fixed_solutions/lru` | 1 | 26 | 0 | lru.py |
| `fixtures/repo_oracle_wallet` | 1 | 25 | 0 | wallet.py |
| `fixtures/_fixed_solutions/merge` | 1 | 23 | 0 | merge.py |
| `core/spine` | 1 | 21 | 0 | __init__.py |
| `docs/results/batch8` | 1 | 19 | 0 | rl_table.py |
| `fixtures/_fixed_solutions/intervals` | 1 | 17 | 0 | intervals.py |
| `fixtures/repo_oracle_toy` | 1 | 6 | 0 | greeter.py |
| `gems/amethyst` | 1 | 5 | 0 | __init__.py |
| `gems/black_tourmaline` | 1 | 5 | 0 | __init__.py |
| `gems/grandidierite` | 1 | 5 | 0 | __init__.py |
| `sandbox` | 1 | 1 | 0 | __init__.py |
