# ETHER Harness — Stable Terminal Control Plane

Primary operator surface under training wheels. **Does not depend on the dashboard.**

Same truth as host_agent and Control Matrix: `artifacts/` + `core.operator_surface`.

## Why

The web dashboard is useful for observation but has been a source of chat races, pending hangs, and UI glitchiness. The harness is the durable path for day-to-day control:

- No FastAPI / browser
- Explicit chat channels (`local` | `grok` | `status` | `git`)
- One-line status strip + interactive REPL
- Same job queue, rates, doctor, swarm as the CLI

## Launch (host)

```powershell
cd C:\Users\Otcde\ETHER
.venv\Scripts\python.exe -m scripts.ether_harness
```

One-shot:

```powershell
.venv\Scripts\python.exe -m scripts.ether_harness --once status
.venv\Scripts\python.exe -m scripts.ether_harness --once phase
.venv\Scripts\python.exe -m scripts.ether_harness --once "chat grok acknowledge harness"
.venv\Scripts\python.exe -m scripts.ether_harness --watch 5
```

Also available via existing CLI (once wired):

```text
ether harness
```

## Commands (REPL)

| Command | Action |
|---------|--------|
| `status` / `st` | heartbeat, phase, last job, queue |
| `phase` / `ph` | honest_rate_eligible, metrics_go, wheels |
| `queue` / `q` | pending + failed |
| `rates` / `r` | phase1 + eligible rates |
| `doctor` | health issues |
| `chat [channel] <msg>` | orchestrate turn; channel = local\|grok\|status\|git |
| `inbox` | recent Grok inbox |
| `clear` | clear chat session (archive kept) |
| `test <fixture> [--live]` | enqueue measurement |
| `swarm [--live]` | wallet + greeter wave |
| `watch [N]` | live status strip |
| `quit` | exit |

## Doctrine (unchanged)

- Training wheels ON until `honest_rate_eligible ≥ 0.99`
- One hypothesis per chat message / job
- Labradorite on non-infra FAIL
- Never auto-lift soft launch from the harness

## Relation to other surfaces

| Surface | Role |
|---------|------|
| **Harness** (`scripts/ether_harness.py`) | Primary stable operator path |
| **CLI** (`scripts/ether_cli.py`) | Scriptable one-shot commands |
| **Dashboard** (`dashboard/`) | Optional visual matrix |
| **host_agent** | Executes jobs; writes artifacts |

All four share `artifacts/` and `core.operator_surface`. No divergent state.
