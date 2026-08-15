# ETHER Master Checklist
**Updated:** 2026-08-15 (MCP CQ + Citrine + Labradorite surfaces)

Soft launch: **BLOCKED** until live tool-path produces an **honest PASS**.  
Training wheels: **ON**. Scripted protect: **GREEN**. FAST-first: **ON**. Mentor doctrine: **LOCKED**.

---

## Phase 1 packages (dashboard source of truth)

| Package | Status | Notes |
|---------|--------|-------|
| 1A Tool-first | **LANDED** | coding_method + honest gate + ToolRuntimeGateHandler |
| 1B AgentState | **LANDED** | core/agent_state.py + evolution_loop wire |
| 1C AST edits | **LANDED** | prefer_patch + surgical doctrine |
| 1D Expand eval | **IN MEASUREMENT** | p1_53 enqueued |

---

## DONE (do not break)

- [x] 1A Tool-first default path
- [x] 1B AgentState skeleton + wire
- [x] 1C AST-aware / surgical edit preference
- [x] tool_runtime + coding_method + prompt_suffix
- [x] Direct hard scripted **5/5**
- [x] Pipeline hard scripted **5/5**
- [x] is_honest_tool_path_pass + ToolRuntimeGateHandler
- [x] job_class FAST/LIVE + FAST-first host sort
- [x] Phase board evidence-based (no more UNKNOWN)
- [x] Mentor doctrine + lessons 001–025

---

## REMAINING — P0 (batch flex in flight)

- [ ] **Pipeline live tool-path lift under 4B** (honest) — `00_p1_53_live_tool_path_honest` enqueued (continue_on_fail)
- [ ] Soft launch authorization (requires above)

---

## Batch flex (Critical/High from super-auditor)

- [x] Enqueued `00_p1_53_live_tool_path_honest`
- [x] Enqueued `01_lora_continuous_dry_tick` (C1)
- [x] Enqueued `02_swarm_parallel_gems_smoke` (C2)
- [x] Enqueued `03_ctx_compress_v0` (H1)
- [x] Enqueued `04_plan_confidence_replan` (H3)
- [x] Enqueued `05_multi_file_ast_tx` (H4)

All respect FAST-first, one-hypothesis, training wheels, Labradorite on FAIL.

---

## MCP Swarm Integration (new)

Architecture (live):
```
ETHER Orchestrator (Selenite + ToolRuntime + honest gate)
  MCP Client(s)  ──stdio / in-process──►
    Clear Quartz MCP  (tools: execute_code, run_project_tests, sandbox_health)
    Citrine MCP       (resources: health/collections; tools: search_memory, ...)
    Labradorite MCP   (tools: critique_code, profile_complexity)
    (Rose/Selenite future)
```

- [x] **CQ MCP**: `gems/clear_quartz/mcp_server.py` + `tests/test_mcp_clear_quartz.py`
- [x] **Citrine MCP**: `gems/citrine/mcp_server.py` + `tests/test_mcp_citrine.py` + job `00_mcp_citrine_01`
- [x] **Labradorite MCP**: `gems/labradorite/mcp_server.py` + `tests/test_mcp_labradorite.py` + job `00_mcp_lab_01`
- [ ] Wire concurrent MCP calls into `swarm_parallel_gems_smoke`
- [ ] Thin MCP Client helper in core (in-process preferred for local-first)
- [ ] Optional: promote full ETHER loop as MCP server later

---

## Mentor secret sauce (locked)

1. Observe → one tool → Observe
2. Tests first → minimal source → surgical apply_patch → run_tests
3. no_progress after 3 stagnant → typed FAIL → Labradorite → smallest experiment
4. Scoreboards are truth. No generate-fallback PASS.
5. One hypothesis per cycle. Hardware honesty (≤4B).

**Goal skill lock:** Phase 1 gate remains closed until 1D honest live PASS.
