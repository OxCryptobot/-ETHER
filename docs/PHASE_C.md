# Phase C — Tool-first agent runtime

## Goal

Replace generate-only best-of-N with **Observe → tool act → Observe** against
project tests (Phase B oracle).

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | `ToolRuntime` + tools + staging | **CLOSED** |
| 2 | `make_llm_decide_fn` Rose Quartz bridge | **CLOSED** |
| 3 | Pipeline wire behind `ETHER_TOOL_RUNTIME=1` | **CLOSED** (`84f6b4e`) |

## Enable

```bash
ETHER_TOOL_RUNTIME=1
ETHER_TOOL_RUNTIME_FIXTURE=fixtures/repo_oracle_toy   # or wallet
ETHER_TOOL_RUNTIME_STEPS=8
ETHER_TOOL_RUNTIME_SECONDS=180
```

## Measurement

```bash
# Offline harness (no LLM) — proves fixtures + tools
python -m scripts.measure_tool_runtime

# Live primary model (host ≤4B)
python -m scripts.measure_tool_runtime --live --fixture all
```

Scripted baseline must be 2/2 PASS. Live results are the first honest signal
for whether tool-first beats generate-only on these fixtures.

## Safety

- Default **OFF**
- Staging only — never live tree
- Path blocks, timeout, max steps
- Fail closed on unparseable model output

## Not yet

- Shell / arbitrary subprocess
- Curriculum / bandit / flywheel re-enable
