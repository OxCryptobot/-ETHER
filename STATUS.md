# @ETHER Status

**Updated:** 2026-08-14T20:56Z — Host live + self-refilling. Soft launch still BLOCKED until measured pipeline lift is honest.

---

## Live state (origin truth)

- Heartbeat fresh. Foreman steady mode active. Pending ~9 jobs (auto-filled).
- Last job `ss_pipeline_ledger_*` → tool_runtime timeout after 12 steps → `tool_runtime_failed_terminal` (correct, no hang).
- **Direct arm hard pack: 5/5 PASS** (scripted, ~1.5 s).
- **Pipeline live ledger: FAIL** (timeout under 16 steps / 4B). That is the Phase 1 1D gap.

## Permanent solutions landed this sprint

### Host never idle
- `host_agent.py` calls `foreman.tick()` on startup, every empty-pending cycle, and after jobs when depth < 5.
- System runs with or without Grok.

### Queue auto-fills forever
- After curriculum exhaustion → **steady mode**: rotates `ss_direct_hard`, `ss_pipeline_ledger`, `ss_train_gates`, `ss_tool_runtime`, `ss_archive_failed` with unique timestamp IDs.
- BATCH_SIZE=10 enforced.

### Failed jobs cleaned
- `ss_archive_failed` moves noise to `failed_archived/`.
- Playbook recovery still converts recovered FAILs to done/.

### Pipeline stability
- Restored + `tool_runtime_failed_terminal` (closes the 984 s hang class).

## SUPER-AUDITOR alignment (2026-08-14)

Ranked killers accepted. Phase 1 FastTrack order:

1. Hard time allotments + timeout-as-typed-error → forced revise path (IN PROGRESS)
2. Failed → Labradorite critique → smallest experiment → requeue (wired, needs continuous use)
3. Phase 1–7 board fully visible on SUPER APP + “what’s next” from foreman
4. Collector path unification (dashboard reads exactly what host_agent writes)
5. Pipeline god-file extraction finish (LoopRunner spine)
6. Script graveyard purge after measurements captured

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first | COMPLETE |
| 1B AgentState | COMPLETE |
| 1C AST transactional | COMPLETE |
| 1D Measured lift | IN PROGRESS — direct 5/5, pipeline live ledger still timeout |

**Gate to Phase 2:** honest pipeline lift on expanded hard pack (≥10 tasks) + time-discipline contract live + failed-job revise loop green.

Training wheels ON. Soft launch blocked until the gate is green.

## Recovery (only if host dies)

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_ether_host.ps1
```

After first successful launch the launcher keeps it alive. Do not restart under normal conditions.
