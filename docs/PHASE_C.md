# Phase C — Tool-first agent runtime

## Goal

Replace generate-only best-of-N with **Observe → tool act → Observe** against
project tests (Phase B oracle).

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | `ToolRuntime` + tools + staging | **CLOSED** |
| 2 | `make_llm_decide_fn` Rose Quartz bridge | **CLOSED** |
| 3 | Pipeline wire behind `ETHER_TOOL_RUNTIME=1` | **ACTIVE** |

## Enable

```bash
ETHER_TOOL_RUNTIME=1
ETHER_TOOL_RUNTIME_FIXTURE=fixtures/repo_oracle_toy   # or wallet
# optional:
ETHER_TOOL_RUNTIME_STEPS=8
ETHER_TOOL_RUNTIME_SECONDS=180
```

When enabled, `Pipeline.run` calls `run_if_enabled(objective)` before
agent_loop / single-shot generate. On success (`ok` + artifact), generation is
skipped and the artifact continues through sandbox + audit.

## API

```python
from core.tool_runtime import ToolRuntime, make_llm_decide_fn, run_if_enabled

# Offline / tests
decide = make_llm_decide_fn(call_fn=my_mock)
# Live model
decide = make_llm_decide_fn()

rt = ToolRuntime(fixture_root=Path("fixtures/repo_oracle_toy"), decide_fn=decide)
result = rt.run("fix greeter")

# Pipeline entry (returns None when gated off)
result = run_if_enabled("fix greeter", decide_fn=decide)
```

## Safety

- Default **OFF**
- Staging only — never live tree
- Path blocks, timeout, max steps
- Fail closed on unparseable model output

## Not yet

- Shell / arbitrary subprocess
- Curriculum / bandit / flywheel re-enable
- Live-model measurement on host fixtures

## Next

Measure tool-runtime path on greeter/wallet with live primary model
(host ≤4B). Only then consider Phase E learning rehaul.
