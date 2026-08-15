# @ETHER Status

**Updated:** 2026-08-15T03:00Z — **RECOVERED.** Soft launch still **BLOCKED** (live tool-path not proven).

---

## Verified green (post IndentationError fix)

| Scoreboard | Result |
|------------|--------|
| `scoreboard_p1_44_direct` | **5/5 PASS** |
| `scoreboard_p1_44_pipeline` | **5/5 PASS** (tool_runtime_scripted) |
| `tool_runtime.py` compile | **OK** + mentor doctrine |
| Host | Alive; last steady direct hard **PASS** |

## Landed this wave

- Critical un-nest `_system_prompt` on main
- Mentor doctrine + `coding_method` schema
- SUPER APP **What's next** bar (`agent.html` + collector)
- Graveyard 13× apply_*
- pep8 tool, ether_cli, typed timeouts

## Still open

1. Pipeline **live** lift on real tool path (not generate-fallback)
2. Soft launch gate
3. Dual dashboard full unify
4. LoopRunner / god-file
5. FAST/LIVE multi-job workers

## Mentor contract

`docs/APPRENTICE_CODING_DOCTRINE.md` · `core/coding_method.py`

```text
python -m scripts.ether_cli status
python -m scripts.ether_cli next
```
