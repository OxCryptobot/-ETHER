---
name: batchphase
description: Max-swarm batch execution for ETHER phases. Use when user says batch, wave, swarm, phase batch, keep building, max swarm, or batchphase.
metadata:
  version: "5.0"
---

# Batchphase v5

Enqueue 3 to 5 jobs, drain, measure, then the next wave. Never dump the graveyard.

## Rules

- FAST jobs: pytest or publishers only. No Ollama. Timeout <= 120s. ETHER_LLM_CANARY != 1.
- MEASURE jobs: hard LIVE canaries, continue_on_fail true, SEED_DENY, own scoreboard path.
- LIVE eligible: greeter/wallet only until unaided hard pack repeats.
- FIFO names sort. Prefix p3_NN_ so conversions run in order.
- After drain: read last_job plus scoreboard. Convert FAIL to a new id. Never requeue the failed file.
- Pending empty plus heartbeat fresh = idle, not dead. HEAD 9aa1865 is idle liveness — that is healthy.
- Hide playbook_* and ss_* from what shipped. last_job is the completed signal.
- Playbook PASS is teacher skill. It does not increment the living-agent gate.

## Wave shape (post-audit)

1. FAST: units for the mutation that just failed.
2. MEASURE: one hard LIVE fixture, max_steps 12, timeout 180-240.
3. FAST: fail_learn plus queue_hygiene if failed list resurrected.
4. Stop. Do not add greeter samples. Do not blind max_steps retries.
