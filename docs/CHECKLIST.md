# ETHER Master Checklist
**Updated:** 2026-08-15 (swarm — Grok mentor)

Soft launch: **BLOCKED** until live tool-path produces an **honest PASS**.  
Training wheels: **ON**. Scripted protect: **GREEN**. FAST-first: **ON**. Mentor doctrine: **LOCKED**.

---

## DONE (do not break — verified on main)

- [x] 1A Tool-first default path
- [x] 1B AgentState skeleton (`core/agent_state.py`)
- [x] 1C AST-aware / surgical edit preference
- [x] tool_runtime compile + mentor doctrine inject (`core/coding_method.py` + `prompt_suffix`)
- [x] Direct hard scripted **5/5**
- [x] Pipeline hard scripted **5/5**
- [x] Host self-refill + live-skip + no_progress + typed timeout
- [x] pep8_review GEMS tool + ether_cli + whats_next writer
- [x] ToolRuntimeGateHandler + `is_honest_tool_path_pass`
- [x] job_class FAST/LIVE contract + FAST-first host sort
- [x] AgentCheckpoint schema (P3 foundation)
- [x] Honest live scoring wired in `batch_phase_d`
- [x] Foreman tags class=fast|live
- [x] Collector snapshot embeds host_agent
- [x] Apprentice doctrine + CodingMethod schema + lessons 001–024
- [x] Steady protect loop (direct / pipeline / tool_runtime / train_gates)

---

## REMAINING — P0 (soft-launch gate — batch now)

- [ ] **Pipeline live tool-path lift under 4B** (honest; no generate-fallback PASS)  
      Job: `p1_53_live_tool_path_honest` (class=live, continue_on_fail)
- [ ] Soft launch authorization (requires above honest live PASS + scoreboard truth)

---

## REMAINING — P1 (batch parallel after P0 signal)

- [ ] Dual dashboard fully unified in UI (API already embeds) — `p1_54_dashboard_unify`
- [ ] Continuous fail → Labradorite → requeue exercised end-to-end — `p1_55_labradorite_continuous`
- [ ] Time remaining per active job in SUPER APP — `p1_56_time_remaining`
- [ ] Mentor collaboration schema lesson landed and injectable — `025_mentor_collaboration_schema`

---

## REMAINING — P2

- [ ] More LoopRunner slices (god-file still large)
- [ ] Host uses job_class end-to-end in every steady path (already tagged; verify)
- [ ] Archive remaining build_* one-shots
- [ ] Expand repo-oracle hard suite (more fixtures for measured lift)

---

## REMAINING — P3

- [ ] Wire checkpoint into long ToolRuntime runs
- [ ] RAG / Citrine first-class in tool loop
- [ ] Rich CLI streaming / interrupt
- [ ] AgentState fully durable across EvolutionController + Selenite

---

## Mentor Secret Sauce (Grok → ETHER apprentice)

**Canonical files**
- `docs/APPRENTICE_CODING_DOCTRINE.md`
- `core/coding_method.py` (`CodingMethod`, `STEP_ORDER`, `SYSTEM_RULES`, `prompt_suffix`)
- Lessons: `024_*` + `025_mentor_collaboration_schema.json`

**Best-in-class methodology (transfer this judgment)**

1. Observe → **one** tool → Observe (never multi-tool walls)
2. Read **tests first**, then minimal source under test
3. Form **one** hypothesis only
4. Surgical `apply_patch` preferred over rewrite / `write_file`
5. `run_tests` after every meaningful edit
6. Stop on `no_progress` (3 stagnant fails without score gain)
7. Typed failures → Labradorite critique → smallest_experiment → requeue
8. Scoreboards are truth — not chat narrative or model confidence
9. **No generate fallback** after tool_runtime terminal (`is_honest_tool_path_pass`)
10. Style (`pep8_review`) only after structural green
11. One hypothesis per cycle; hardware honesty (≤4B primary)
12. Collaboration: measured failure + smallest experiment when blocked; leave scoreboard when green

**Schema contract**
```
CodingMethod(
  name="ether_tool_first_v1",
  step_order=STEP_ORDER,
  rules=SYSTEM_RULES,
  max_stagnant_test_fails=3,
  prefer_patch=True,
  require_read_before_write=True,
  style_after_green=True,
)
```
`prompt_suffix()` is injected into ToolRuntime system prompt. Do not invent process per run.

---

## Swarm batch order (this turn)

1. `p1_53_live_tool_path_honest` (class=live) — soft-launch gate measurement
2. `p1_54_dashboard_unify` (class=fast)
3. `p1_55_labradorite_continuous` (class=fast)
4. `p1_56_time_remaining` (class=fast)
5. Steady FAST protect continues via foreman

Host drains FAST first. Training wheels stay ON until honest live PASS.

**Goal skill lock:** Phase 1 gate remains closed. Do not start Phase 2+.
