# Operator Surface (OS-1)

Best-in-class local control plane for @ETHER.

## What it is

A single facade (`core/operator_surface.py`) + CLI + Control Matrix APIs that speak the **same language** as `host_agent`:

| Surface | Path |
|---------|------|
| CLI | `python -m scripts.ether_cli <cmd>` |
| Matrix API | `http://127.0.0.1:8787/api/{rates,operator,llm,chat,test}` |
| Chat bus | `artifacts/chat/{inbox,outbox,archive}/` |
| Multi-LLM | `core/multi_llm.py` (Ollama primary + Grok burst) |

## CLI commands

```
ether status          # host heartbeat + last job
ether queue           # pending / failed
ether phase           # phase1_gate snapshot
ether next            # next pending job
ether doctor          # health issues
ether job list
ether job enqueue --file job.json
ether job cancel <id>
ether test wallet --live
ether test greeter --arm direct
ether rates           # phase1 + eligible + multi_llm
ether chat "message"  # post to Grok outbox
ether chat inbox      # read Grok replies
ether git sync        # ff-only or hard-reset to origin
ether tools           # persistent + quarantine
ether learn           # preference + strategy
ether agent           # full status JSON
ether llm             # lane status (fast/live/burst)
```

## Chat bus

Git-backed envelopes. One hypothesis per message.

```json
{
  "id": "chat_YYYYMMDD_HHMMSS_xxxxxx",
  "from": "operator|ether|grok",
  "type": "critique_request|plan|status|recovery|operator|learn|job_request|ack",
  "payload": {},
  "job_id": "optional",
  "requires_reply": true,
  "schema": "ether_chat_v1"
}
```

- ETHER / operator → Grok: write `artifacts/chat/outbox/`
- Grok → ETHER: write `artifacts/chat/inbox/`
- Host agent and Control Matrix both read the same paths.

## Multi-LLM lanes

| Lane | Backend | When |
|------|---------|------|
| fast | Ollama ≤4B (qwen3.5:4b family) | default |
| live | same host model under live_budget | gate_sample / measurement |
| burst | Grok / xAI (`ETHER_BURST=1` + API key) | hard fails only, budget-gated |

Hardware lock preserved: host never auto-selects >4B.

## Doctrine

- Training wheels stay ON until measured lift.
- One hypothesis per job / chat message.
- Labradorite mandatory on non-infra FAIL.
- All results land in the same `artifacts/` host_agent already owns.
- No second scoring path. No budget bumps without critique.

## Synergy with host_agent

`operator_surface.enqueue_job` applies `live_budget` the same way host_agent does.
`git_sync` uses the identical ff-only → hard-reset policy.
Test jobs use `class=gate_sample` + `continue_on_fail=true` so outcomes are always countable.

## Next (OS-2+)

- Chat panel in agent.html
- Speech dictation (browser SpeechRecognition → chat post)
- File upload endpoint → quarantine or fixtures
- MCP tool surface via CLI
- Swarm / multifile as first-class `ether swarm` / `ether multifile`
