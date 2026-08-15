# ETHER Master Checklist (2026-08-15)

Soft launch: **BLOCKED** until live tool-path produces an honest PASS.  
Training wheels: **ON**. Scripted protect: **GREEN**.

## DONE (do not break)

- [x] 1A Tool-first / 1B AgentState / 1C AST edits
- [x] tool_runtime compile OK + mentor doctrine inject
- [x] Direct hard scripted **5/5** (p1_44, p1_46, p1_49)
- [x] Pipeline hard scripted **5/5** (p1_44, p1_49)
- [x] Host self-refill + live-skip + no_progress + typed timeout
- [x] pep8_review GEMS tool + ether_cli + whats_next writer
- [x] 13× apply_* → graveyard
- [x] Apprentice doctrine + coding_method schema + lessons
- [x] SUPER APP What's next bar + collector whats_next field
- [x] ToolRuntimeGateHandler + is_honest_tool_path_pass
- [x] job_class FAST/LIVE contract + FAST-first host sort
- [x] AgentCheckpoint schema (P3 foundation)
- [x] live_tool_path_timeout Labradorite lesson
- [x] Honest live scoring in batch_phase_d (on main, verified by p1_49)
- [x] FAST-first host list_pending (on main)
- [x] Foreman tags class=fast|live (on main)
- [x] Collector snapshot embeds host_agent (on main)
- [x] p1_49 batch phase wave PASS (dual-arm scripted hard + mentor + whats_next)

## REMAINING — P0 (soft-launch gate)

- [ ] Pipeline **live tool-path** lift under 4B (honest; no generate-fallback PASS)
- [ ] Soft launch authorization (requires above)

## REMAINING — P1

- [ ] Dual dashboard fully unified in UI (API already embeds host_agent)
- [ ] Continuous fail→Labradorite→requeue exercised end-to-end (lesson-driven)
- [ ] Time remaining per active job in SUPER APP

## REMAINING — P2

- [ ] More LoopRunner slices (god-file still large)
- [ ] Host uses job_class end-to-end in every steady path (already tagged)
- [ ] Archive remaining build_* one-shots

## REMAINING — P3

- [ ] Wire checkpoint into long ToolRuntime runs
- [ ] RAG/Citrine first-class in tool loop
- [ ] Rich CLI streaming / interrupt

## Mentor secret sauce (locked)

Files: `docs/APPRENTICE_CODING_DOCTRINE.md` · `core/coding_method.py` · `artifacts/lessons/mentor_coding_loop.json` · `artifacts/lessons/024_mentor_coding_method_v2.json`

1. Observe → **one** tool → Observe
2. Read **tests first**, then minimal source
3. Surgical `apply_patch` preferred over rewrite
4. `run_tests` after every meaningful edit
5. Stop on `no_progress` (3 stagnant fails)
6. Typed failures → critique → smallest experiment → requeue
7. Scoreboards are truth — not chat narrative
8. **No generate fallback** after tool_runtime terminal
9. Style (`pep8_review`) only after structural green
10. One hypothesis per cycle
