# @ETHER Status

**Updated:** 2026-08-15T01:45Z — **NOT DONE.** Soft launch BLOCKED. Training wheels ON.

Host heartbeat healthy. Last steady: **direct hard PASS**.

---

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A–1C | **COMPLETE** |
| 1D Measured lift | Scripted **GREEN**; live **OPEN** |

See **`docs/BACKLOG.md`** for the ordered remaining list.

## Building now

- `p1_41` — move 13 `apply_*` one-shots → `scripts/_graveyard/` + write `whats_next` + protect direct 5/5
- Archive tool: `python -m scripts.archive_script_graveyard --apply`

## Still open (short)

1. Pipeline live under 4B  
2. SUPER APP bind `whats_next.json`  
3. Dual dashboard unify  
4. LoopRunner finish / god-file  
5. Multi-job FAST pool  

```text
python -m scripts.ether_cli status
python -m scripts.ether_cli next
python -m scripts.ether_cli doctor
```
