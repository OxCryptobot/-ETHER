# Phase C — Tool-first agent runtime

## Goal

Replace generate-only best-of-N with **Observe → tool act → Observe** against
project tests (Phase B oracle).

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | `ToolRuntime` + tools + staging | **CLOSED** |
| 2 | `make_llm_decide_fn` Rose Quartz bridge | **CLOSED** |
| 3 | Pipeline wire behind `ETHER_TOOL_RUNTIME=1` | **CLOSED** |
| measure | easy+hard live on host ≤4B | **CLOSED 7/7** |

## Final measurement (2026-08-01)

| Tier | Live result |
|------|-------------|
| easy (greeter, wallet) | **2/2** |
| hard (lru, merge, ledger, topo, intervals) | **5/5** |
| **Total** | **7/7** |

Key fixes: nested-JSON `parse_action`, `_retry` on unparseable (not `done`),
explicit objectives for cycle/multi-bug, forced read tests+source before write.

## Enable

```bash
ETHER_TOOL_RUNTIME=1
ETHER_TOOL_RUNTIME_FIXTURE=fixtures/repo_oracle_toy
ETHER_TOOL_RUNTIME_STEPS=8
ETHER_TOOL_RUNTIME_SECONDS=180
```

## Safety

- Default **OFF**
- Staging only — never live tree
- Path blocks, timeout, max steps
- Fail closed on unparseable model output

## Not yet

- Shell / arbitrary subprocess
- Curriculum / bandit / flywheel re-enable
- Pipeline e2e live measure → **Phase D**
