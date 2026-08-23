# ETHER Harness v2 — Hermes-class Terminal Control Plane

Primary operator surface under training wheels. **No dashboard required.**

Patterns borrowed from Hermes Agent (Nous Research): slash commands, shell mode,
agent-default free text, session log, skills, wave swarm — adapted to ETHER's
measured doctrine and `operator_surface` truth.

## Launch

```powershell
cd C:\Users\Otcde\ETHER
.venv\Scripts\python.exe -m scripts.ether_harness
```

One-shot / watch:

```powershell
.venv\Scripts\python.exe -m scripts.ether_harness --once /status
.venv\Scripts\python.exe -m scripts.ether_harness --once /phase
.venv\Scripts\python.exe -m scripts.ether_harness --once /wave 4
.venv\Scripts\python.exe -m scripts.ether_harness --watch 4
```

CLI peer: `python -m scripts.ether_cli harness`

## Hermes-class features

| Feature | How |
|---------|-----|
| Slash commands | `/status` `/phase` `/swarm` `/skills` `/goal` `/wave` … |
| Shell mode | `!git status` — zero LLM cost, not in chat history |
| Agent-default | Free text → local orchestrated turn (one hypothesis) |
| Explicit channels | `chat grok …` / `chat local …` / `chat status …` |
| Session log | `artifacts/harness_session.jsonl` · `/session` |
| Skills | `/skills` list · `/skills show <id>` |
| Wave / max swarm | `/wave 4` or `/swarm --live` (easy fixtures only) |
| Live strip | `/watch 4` or `--watch 4` |
| Tools / MCP | `/tools` `/mcp` |
| Goal board | `/goal` — measured phase1 gate only |

## Doctrine (locked)

- Training wheels **ON** until `honest_rate_eligible ≥ 0.99`
- One hypothesis per chat message / job
- Easy fixtures only for live waves (greeter, wallet)
- Labradorite on non-infra FAIL
- Never auto-lift `ETHER_SOFT_LAUNCH` from the harness

## Surfaces

| Surface | Role |
|---------|------|
| **Harness v2** | Primary stable operator path (Hermes-class) |
| **CLI** (`ether_cli.py`) | Scriptable one-shots |
| **Dashboard** | Optional visual matrix |
| **host_agent** | Executes jobs; writes artifacts |

All share `artifacts/` + `core.operator_surface`.
