# ETHER Master Checklist (2026-08-15)

Soft launch: **BLOCKED**. Training wheels: **ON**.

## DONE

- [x] 1A / 1B / 1C
- [x] Direct + pipeline hard scripted 5/5 (pre-incident baseline)
- [x] Host self-refill, live-skip, no_progress, typed timeouts
- [x] pep8_review tool, ether_cli, whats_next writer
- [x] Archive 13× apply_* → scripts/_graveyard/
- [x] Apprentice doctrine + coding_method schema + lesson
- [x] Dashboard collector exposes whats_next
- [x] **tool_runtime IndentationError FIXED on main (compile OK + doctrine)**

## IN FLIGHT

- [ ] p1_44: pytest doctrine + dual scripted rebaseline after fix
- [ ] Confirm direct hard PASS post-fix
- [ ] Confirm pipeline scripted 5/5 post-fix

## REMAINING — P0

- [ ] Pipeline **live** lift on **tool path** (not generate-fallback)
- [ ] Soft launch only after live tool-path truth

## REMAINING — P1

- [ ] SUPER APP UI binds whats_next
- [ ] Dual dashboard → one collector
- [ ] Continuous fail → Labradorite → requeue

## REMAINING — P2

- [ ] LoopRunner stage extraction / kill god-file
- [ ] Host FAST vs LIVE workers
- [ ] Archive remaining build_* bloat

## REMAINING — P3

- [ ] Checkpoint/resume, RAG-first, rich CLI

## Mentor secret sauce (always on)

1. Observe → one tool → Observe
2. Read tests before source
3. Surgical apply_patch
4. run_tests after every edit
5. no_progress after 3 stagnant fails
6. Typed failures → critique → requeue
7. Scoreboards are truth
8. No generate fallback after tool_runtime terminal

`docs/APPRENTICE_CODING_DOCTRINE.md` · `core/coding_method.py`
