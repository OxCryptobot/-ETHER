# @ETHER Status

**Updated:** 2026-08-14T22:42Z — **NOT DONE.** Soft launch BLOCKED. Training wheels ON.

---

## Goal skill — Phase 1 board (truth)

| Package | Status |
|---------|--------|
| **1A Tool-first default** | **COMPLETE** |
| **1B AgentState durable** | **COMPLETE** |
| **1C AST transactional edits** | **COMPLETE** |
| **1D Measured lift** | Scripted **GREEN** (direct + pipeline hard 5/5, including parallel). Live under 4B **OPEN**. |

**Gate to Phase 2:** still blocked — live pipeline lift not proven; soft launch not authorized.

## This batch

- `core/failure_types.py` — typed failure taxonomy
- `host_agent` stamps `failure_type=timeout` on step/job TimeoutExpired
- modules.yaml registered
- Host healthy; last steady direct hard **PASS**

## Verified green (do not regress)

- Direct hard scripted 5/5
- Pipeline hard scripted 5/5 (serial + parallel)
- Self-refill + live-skip + no_progress + pep8_review tool + ether_cli

## Still open

- Pipeline live lift (4B budget)
- God-file extraction
- Dual dashboard unify
- Graveyard archive (inventory only so far)
- Full SUPER APP what’s-next UI

```text
python -m scripts.ether_cli status
python -m scripts.ether_cli next
python -m scripts.ether_cli doctor
```
