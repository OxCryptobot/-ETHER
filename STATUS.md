# @ETHER Status

**Updated:** 2026-08-14T21:34Z — Scripted pipeline path fixed. Soft launch still BLOCKED.

---

## Live state

- Host Agent: alive, auto-refilling, direct hard 5/5 PASS.
- **Fix landed:** `batch_phase_d` pipeline `mode=scripted` now uses ToolRuntime scripted path (final scoreboard, not sentinel-only).
- **p1_35** enqueued: pipeline scripted hard pack measurement.
- Timeout → revise lesson wired (`timeout_budget_exhaust`).
- Pipeline **live** ledger still fails under 4B (expected; terminal harden correct).

## Gap tracker (honest)

| Gap | Status |
|-----|--------|
| True scripted pipeline measurement | **FIXED this batch** |
| Phase 1 1D measured lift | IN PROGRESS — waiting p1_35 scoreboard |
| Hard time allotments + timeout→revise | Lesson wired; full contract still next |
| Closed Labradorite loop | Partial — playbook lesson live |
| SUPER APP / Control Matrix | Partial — Phase board parser fixed |
| Pipeline god-file | Open (extraction after measurements) |
| Script graveyard | Open (purge after scores captured) |
| Concurrency / multi-job | Open (later) |
| Checkpoint/resume | Open (later) |

## FastTrack order

1. Scripted pipeline measurement → **code fixed**, waiting host result on p1_35
2. Time-allotment contract + continuous revise path
3. Labradorite loop kept green
4. Collector/dashboard unification
5. LoopRunner extraction
6. Graveyard purge

## Phase 1 board

| Package | Status |
|---------|--------|
| 1A Tool-first | COMPLETE |
| 1B AgentState | COMPLETE |
| 1C AST transactional | COMPLETE |
| 1D Measured lift | IN PROGRESS — direct 5/5, pipeline scripted hard pack running |

**Gate:** honest pipeline lift numbers + time discipline + revise loop green.

Training wheels ON. Soft launch blocked.

## Recovery (only if host dies)

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_ether_host.ps1
```
