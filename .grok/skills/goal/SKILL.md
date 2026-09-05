---
name: goal
description: Complete Ether Goals. Use when user says goal, phase, roadmap, leftover, living agent, or what ETHER is building toward.
metadata:
  version: "6.0"
  type: doctrine
---

# @ETHER Goals v6

## Identity

Local-first super-agent. Three pillars: Modular Intelligence (8 gems), Verified Execution (pytest judge), Controlled Evolution (stub fabricate + flywheel).

FAST chair is qwen3.5:4b on the box. LIVE scales: local-large when VRAM ≥ 12GB, outsource when keyed (Grok/xAI/OpenAI). Not a swarm. `MAX_LIVE_AGENTS=1`.

## Living-agent gate — MET

Unaided merge ×3 and ledger ×3, `policy=model`, `replace_once` from `bug_comments`. Wheels stay ON. Dual chat is the only operator surface.

## Leftover (~10%)

- LoRA train off-box (≥12GB)
- Split 76kB `pipeline.py`
- More unaided fixtures (4B hours)
- Operator sets `ETHER_OUTSOURCE=1` + API key for LIVE

## Doctrine lock

- Tool-first. Generate-fallback is never PASS.
- Lessons from **tool traces**, not playbooks.
- Playbook PASS is `teacher_playbook`, never `model_skill`.
- Medic stands down while idle + fresh heartbeat.
- Dual chat chrome is locked.

## Now

1. leftover_reverify FAST gate (p1–p4 + scale + pep8).
2. Living pack on host (`merge`/`ledger`/`lru`) — not FAST theatre.
3. Scale LIVE when hardware or keys exist.
