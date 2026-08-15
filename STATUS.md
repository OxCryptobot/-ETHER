# @ETHER Status

**Updated:** 2026-08-15T03:10Z — Soft launch **BLOCKED**. Scripted green. Live tool-path measured **FAIL** (honest).

---

## Diagnosis (real)

| Symptom | Root cause | Real fix |
|---------|------------|----------|
| Live ledger timeout ~5 min | 4B model burns steps without green tests | Terminal harden + live-skip + **honest score reject** |
| False green on generate fallback | Scoreboard counted ok=true after tool fail | `is_honest_tool_path_pass` in batch_phase_d |
| Queue stalled by live jobs | FIFO ignored class | **FAST-first** host pick |
| Playbooks miss timeout | step_fail without failure_type | Enrich from scoreboard degraded |
| Dual dashboard drift | Separate collectors | Embed host_agent in snapshot |

## p1_47 applies

1. Honest live scoring (`patch_honest_live_score`)
2. FAST-first host (`patch_host_fast_first`)
3. Foreman `class=fast|live` (`patch_foreman_job_class`)
4. Dashboard unify (`patch_collector_unify`)
5. Protect scripted 5/5

## Still cannot be coded away

**Live tool-path lift under 4B** — model capacity. Plumbing is correct; soft launch stays blocked until live tool path passes without generate-fallback.

```text
python -m scripts.ether_cli status
```
