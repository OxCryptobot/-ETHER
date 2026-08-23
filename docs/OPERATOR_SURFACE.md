# Operator Surface — Best-in-Class Professional Control Plane

Single facade for CLI + Harness + Control Matrix + host_agent. Same `artifacts/` paths. Training wheels ON.

## Primary path: Harness (stable terminal)

Prefer the harness when the dashboard feels unstable or chat races appear.

```powershell
.venv\Scripts\python.exe -m scripts.ether_harness
# or
.venv\Scripts\python.exe -m scripts.ether_cli harness
```

See `docs/HARNESS.md` for full command list, watch mode, and explicit chat channels.

## CLI commands

```
ether status | queue | phase | next | doctor | harness
ether job list | enqueue --file <json> | cancel <id>
ether test <fixture> [--live] [--arm direct]
ether rates
ether chat "message" [--channel auto|local|grok|status|git] | chat inbox
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

Use **harness** or `ether chat --channel grok` for reliable escalation (avoids dashboard pending races).

## Doctrine

- One hypothesis per job / chat message
- Labradorite on non-infra FAIL
- Measurement jobs always → done/
- Never lift wheels until honest_rate_eligible ≥ 0.99
