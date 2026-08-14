# @ETHER Status

**Updated:** 2026-08-14 — Package 1C landed + wired into tool_runtime write_file (AST gate). Phase 1 batch queued (p1_04b → p1_06 → p1_07 → p1_08). Host still offline since 2026-08-08; recovery already issued once. Training wheels stay ON.

Read `docs/FINDINGS.md` and `docs/GEM_EVOLUTION.md` before changing anything.

---

## Non-negotiable doctrine (2026-08-08)

- **GEMS are core.** Streamline only. Never remove or dilute the gem topology.
- **Training wheels stay ON** until measured lift on expanded repo-oracle suite.
- One hypothesis per job/cycle. Labradorite structured critique mandatory on non-infra FAIL.
- LoRA / weight updates gated by dual flags + holdout. Dry-run is the only default.
- **Tool-first is the required direction.** Generation-first is no longer the default target.

---

## Where the project actually is

| | |
|---|---|
| Tests | **770+** (1C suite + AST-gate tests) |
| Verification | held-out grading, mutation score 0.966 |
| Leak channels closed | **7** |
| `main` | green on fresh clone for core tests |
| **Does ETHER beat a bare model on holdout generate?** | **No** (ablation stands) |
| **Does tool-runtime beat bare on hard repo-oracle pack?** | **Yes** (Phase D 5/5) |
| AgentState | skeleton landed + wired into EvolutionController |
| LoRA path | data prep + dry-run live; real train dual-flag gated |
| Evolution loop | introspection mandatory; __main__ hardened; tw_e08 PASS |
| **Tool-first default (1A)** | **LANDED** |
| **Dashboard SUPER APP** | **LANDED** |
| **Foreman** | **REVAMPED** + Phase 1 curriculum extended |
| **AST transactional edits (1C)** | **LANDED + WIRED** into tool_runtime write_file |

### Holdout generate (unchanged)

| model | bare | bare+sys | ether |
|---|---|---|---|
| `qwen2.5:3b` | 0.317 | 0.333 | 0.292 |

`ether − bare+sys = −0.042`. Agent loop remains net negative on pure generate.

### Phase D — hard repo-oracle (host `qwen3.5:4b`)

| arm | hard 5 |
|-----|--------|
| **direct** (ToolRuntime) | **5/5** |
| **pipeline** | **5/5** |
| **bare** | **0/5** |

---

## Active rollout

### Phase 1 — Critical Fixes (IN PROGRESS)

| Package | Status | Success criteria |
|---------|--------|------------------|
| 1A Tool-first default | **LANDED** | tool_runtime default under wheels; Phase D still 5/5 |
| 1B AgentState durable | **WIRED** | create/save/load; shared by gems |
| 1C AST transactional edits | **LANDED + WIRED** | EditTransaction + AST-gate on write_file |
| 1D Expand eval + close FAILs | **IN PROGRESS** | batch queued: p1_04b, p1_06, p1_07, p1_08 |

**Gate to Phase 2:** Tool-first live, AgentState durable, ≥10 hard tasks measured with pipeline lift, evolution FAILs closed.

### Phases 2–7
Locked behind Phase 1 gate.

---

## Pending host batch (FIFO)

1. `p1_04b_measure_pipeline_lift_verbose` — pipeline hard + scoreboard
2. `p1_06_ast_transaction_tests` — verify 1C suite
3. `p1_07_measure_direct_hard` — direct baseline
4. `p1_08_expand_hard_count` — repo-oracle gate toward ≥10

## Next action only

1. Host recovery (already issued once) — poll artifacts/host_agent_status.json
2. Drain the 4 pending jobs; read scoreboards
3. Only after measured lift: discuss wheels
