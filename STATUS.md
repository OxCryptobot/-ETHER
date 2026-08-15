# @ETHER Status

**Updated:** 2026-08-15 19:01Z — Phase 2.5 LoRA dry tick landed. Soft launch **BLOCKED**.

## Law
**Test after every build. Do not break working paths.**
- `ETHER_LOOP_RUNNER=0` default
- `ETHER_SYMBOL_INDEX=0` default
- LoRA: dry tick only; real train needs `ETHER_LORA_TRAIN=1` + `ETHER_LORA_PROMOTE=1`

## Host
Alive. Job `p2_5_lora_dry_tick_verify` enqueued (pytest suite + dry tick CLI).

## Phase 2 map

| Phase | Item | Status |
|-------|------|--------|
| 2.1 | PlanState replan | done |
| 2.2 | Multi-file AST tx | done |
| 2.3 | Orchestration slice | done |
| 2.4 | Symbol/file index v0 | done |
| **2.5** | **LoRA dry tick only** | **done** |

**Phase 2 complete pending host green on verify jobs.**

## Phase 3 (next after green)
1. Soft-launch measurement: publish honest live rates on expanded hard suite
2. Wire decide_tool_first_terminal into Pipeline (behavior-preserving)
3. Steady template: ss_lora_dry_tick + ss_honest_live_report

Training wheels ON.
