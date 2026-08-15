# ETHER Master Checklist (2026-08-15)

Soft launch: **BLOCKED**. Training wheels: **ON**.

## DONE

- [x] 1A Tool-first default
- [x] 1B AgentState durable
- [x] 1C AST transactional edits
- [x] Direct hard scripted 5/5
- [x] Pipeline hard scripted 5/5 (serial)
- [x] Pipeline hard scripted 5/5 (parallel ThreadPool)
- [x] Host self-refill / foreman.tick never idle
- [x] Live-skip after pipeline budget_exhaust
- [x] no_progress early abort (3 stagnant run_tests)
- [x] Typed `failure_type` on host timeout
- [x] Timeout playbook lesson + failure_type match
- [x] `pep8_review` GEMS tool in TOOL_SPECS
- [x] `ether_cli` status/queue/phase/next/doctor
- [x] `write_whats_next` + foreman tick refresh
- [x] Archive 13× `apply_*` → `scripts/_graveyard/`
- [x] `docs/BACKLOG.md`

## IN FLIGHT / THIS SWARM

- [ ] Apprentice coding doctrine (mentor → ETHER)
- [ ] `core/coding_method.py` schema for agents
- [ ] Doctrine injected into ToolRuntime system prompt
- [ ] Lesson JSON for coding method
- [ ] whats_next always on disk after tick
- [ ] Regression: direct hard + pep8 tool + doctrine import

## REMAINING — P0 (gate)

- [ ] Pipeline **live** lift under 4B on hard pack
- [ ] Soft-launch gate decision (only after live truth)

## REMAINING — P1 (ops)

- [ ] Failed → Labradorite → requeue continuous (not partial)
- [ ] SUPER APP binds `artifacts/whats_next.json`
- [ ] Single collector path (kill dual dashboard drift)
- [ ] Time remaining shown per active job in UI

## REMAINING — P2 (architecture)

- [ ] Next LoopRunner stage extraction from pipeline.py
- [ ] pipeline.py thin façade (god-file dead)
- [ ] Inventory + archive `build_*` one-shots
- [ ] Host FAST vs LIVE job classes (parallel workers)

## REMAINING — P3 (later)

- [ ] Checkpoint/resume long agent runs
- [ ] Citrine/RAG first-class in tool_runtime
- [ ] CLI streaming + interrupt + session resume
- [ ] Multi-host mesh (not needed solo)

## Non-goals (do not start)

- [ ] Soft launch without 1D live truth
- [ ] Training wheels off
- [ ] 7B+ auto-pull on GTX 1650
