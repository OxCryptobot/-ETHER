# ETHER remaining backlog (2026-08-15)

Training wheels ON. Soft launch **BLOCKED** until 1D live improves or gate policy is explicitly changed.

## Done (do not break)

- 1A / 1B / 1C complete
- Direct + pipeline hard **scripted** 5/5 (serial + parallel)
- Host self-refill, live-skip, no_progress, typed `failure_type`
- `pep8_review` tool for GEMS, `ether_cli`, timeout playbook lesson
- `whats_next` writer + foreman tick refresh

## Build now (this wave)

| # | Item | Owner path |
|---|------|------------|
| 1 | Archive apply_* one-shots → `scripts/_graveyard/` | `archive_script_graveyard.py --apply` |
| 2 | Ensure `artifacts/whats_next.json` always present | host job + tick |
| 3 | Keep direct hard baseline green | steady templates |

## Still open (ordered)

### P0 — Phase 1 gate
1. **Pipeline live lift under 4B** — model budget; not a plumbing gap
2. Soft launch authorization — blocked by (1)

### P1 — Ops contracts
3. Full failed → Labradorite → requeue continuity (partial; playbooks exist)
4. SUPER APP / Control Matrix bind `whats_next.json` (UI)
5. Collector path unification (dual dashboard)

### P2 — Architecture
6. Finish LoopRunner extraction (kill pipeline god-file)
7. Remaining `build_*` bloat audit after apply_* archive
8. Host FAST vs LIVE worker classes (multi-job)

### P3 — Later
9. Checkpoint/resume for long runs
10. Memory/RAG first-class in tool_runtime
11. Professional CLI streaming / interrupt model

## Explicit non-goals right now

- Soft launch
- Training wheels off
- Multi-host mesh
- 7B+ models on this hardware
