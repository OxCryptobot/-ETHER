# ETHER Master Checklist
**Updated:** 2026-08-15 (phase board FIXED — evidence-based)

Soft launch: **BLOCKED** until live tool-path produces an **honest PASS**.  
Training wheels: **ON**. Scripted protect: **GREEN**. FAST-first: **ON**. Mentor doctrine: **LOCKED**.

---

## Phase 1 packages (dashboard source of truth)

| Package | Status | Notes |
|---------|--------|-------|
| 1A Tool-first | **LANDED** | coding_method + honest gate + ToolRuntimeGateHandler |
| 1B AgentState | **LANDED** | core/agent_state.py + evolution_loop wire |
| 1C AST edits | **LANDED** | prefer_patch + surgical doctrine |
| 1D Expand eval | **BLOCKED** | Needs honest live tool-path PASS |

Dashboard was showing UNKNOWN because collector parsed a fragile STATUS.md. Fixed: evidence-based detection in `dashboard/collector_host_agent.py`.

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

## REMAINING — P0

- [ ] **Pipeline live tool-path lift under 4B** (honest) — `p1_53_live_tool_path_honest` requeued
- [ ] Soft launch authorization (requires above)

---

## REMAINING — P1

- [x] Dual dashboard path smoke (p1_54 done)
- [x] Labradorite path presence (p1_55 done)
- [x] Time remaining readiness (p1_56 done)
- [x] Mentor collaboration schema lesson 025

---

## REMAINING — P2 / P3

- [ ] More LoopRunner slices
- [ ] Expand hard oracle suite
- [ ] Wire checkpoint into long ToolRuntime runs
- [ ] RAG / Citrine first-class
- [ ] Full AgentState durability across EvolutionController + Selenite
- [ ] Rich CLI streaming / interrupt

---

## Mentor secret sauce (locked)

1. Observe → one tool → Observe
2. Tests first → minimal source → surgical apply_patch → run_tests
3. no_progress after 3 stagnant → typed FAIL → Labradorite → smallest experiment
4. Scoreboards are truth. No generate-fallback PASS.
5. One hypothesis per cycle. Hardware honesty (≤4B).

**Goal skill lock:** Phase 1 gate remains closed until 1D honest live PASS.
