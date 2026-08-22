# Operator Surface — Best-in-Class Professional Control Plane

Single facade for CLI + Control Matrix + host_agent. Same `artifacts/` paths. Training wheels ON.

## Commands

```
ether status | queue | phase | next | doctor
ether job list | enqueue --file <json> | cancel <id>
ether test <fixture> [--live] [--arm direct]
ether rates
ether chat "message" | chat inbox
ether git sync
ether tools | learn | agent | llm
ether skill list | skill show <id>
ether upload <path> [--dest uploads|quarantine]
ether swarm [--live] [--fixtures wallet,greeter]
ether multifile "objective text"
ether speech "transcribed text"
ether mcp
```

## Multi-LLM

| Lane | Backend |
|------|--------|
| fast / live | Ollama ≤4B (qwen3.5:4b family) |
| burst | Grok / xAI when `ETHER_BURST=1` + API key |

## Chat bus

`artifacts/chat/{inbox,outbox,archive}/` — git-backed envelopes. Grok reads outbox, writes inbox. host_agent can poll outbox for critique/recovery.

## Doctrine

- One hypothesis per job / chat message
- Labradorite on non-infra FAIL
- Measurement jobs always → done/
- Never lift wheels until honest_rate_eligible ≥ 0.99
