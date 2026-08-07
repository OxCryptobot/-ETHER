# Full backlog from 2026-08-07 — mapped to host jobs

Agent drains `artifacts/jobs/pending/` FIFO by filename.
Poll idle = 1s. Jobs in queue run with zero gap.

## Already done (do not re-queue)
- Phase G tools: grep, glob, apply_patch, rollback on main
- host_agent + dashboard /agent
- phaseg_verify_003 PASS, land_runtime_001 PASS

## Phase 1 — Tool surface close
| Job | Work |
|-----|------|
| `p1_01_ruff_tests` | pytest ruff_gate + tool_runtime |
| `p1_02_hard_scripted` | batch_phase_d direct scripted hard 5/5 |
| `p1_03_findings_g` | append FINDINGS Phase G close (host echo/check) |

## Phase 2 — Verification spine
| Job | Work |
|-----|------|
| `p2_01_cq_oracle` | pytest clear_quartz multifile + repo_oracle* |
| `p2_02_pipeline_import` | import Pipeline + tool path smoke |
| `p2_03_measure_scripted` | measure_pipeline_tool ledger path direct scripted if available |

## Phase 3 — Memory / no-leak
| Job | Work |
|-----|------|
| `p3_01_prompt_holdout` | pytest prompt_guard + holdout |
| `p3_02_experience_safe` | pytest experience / rag filters if present |

## Phase 4 — Planning
| Job | Work |
|-----|------|
| `p4_01_selenite` | pytest selenite/plan tests if present else scaffold marker |
| `p4_02_plan_import` | import selenite modules |

## Phase 5 — Repo-scale edits
| Job | Work |
|-----|------|
| `p5_01_patch_multifile` | pytest tool_runtime + clear_quartz multifile |
| `p5_02_phase_f_scripted` | batch_phase_f direct scripted |

## Phase 6 — Swarm (gated offline)
| Job | Work |
|-----|------|
| `p6_01_swarm_scaffold` | core/swarm.py exists check / create stub status |
| `p6_02_swarm_import` | import swarm stub |

## Phase 7 — Controlled evolution (offline)
| Job | Work |
|-----|------|
| `p7_01_flywheel_off` | assert FLYWHEEL_PUSH default off |
| `p7_02_boN_off` | assert agent loop / BoN not default-on |

## Continuous gates (repeatable)
| Job | Work |
|-----|------|
| `z_gate_pytest_core` | broad offline pytest slice |
| `z_gate_hard_scripted` | hard scripted 5/5 |
