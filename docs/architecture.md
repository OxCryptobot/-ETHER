# @ETHER Architecture

```
User
  ↓
CLI (ether)
  ↓
Pipeline / Orchestrator
  ↓
Registry
  ↓
┌──────────────────────────────────────┐
│ Clear Quartz  Rose Quartz  Citrine          │
│ Sandbox       Router       Memory           │
├──────────────────────────────────────┤
│ Selenite      Amethyst     Black Tourmaline │
│ Planner       Evolution    Security         │
├──────────────────────────────────────┤
│ Labradorite   Grandidierite                 │
│ Critique      Meta-extension                │
└──────────────────────────────────────┘
```

## Pipeline flow

1. Selenite plans
2. Rose Quartz generates code
3. Clear Quartz executes in Docker sandbox
4. Black Tourmaline audits
5. Optional Labradorite critique
6. Amethyst logs + result saved under `memory/runs/`

## Security model

- Primary boundary: Docker (`--network none`, `--read-only`, resource limits)
- Defense-in-depth: AST + manifest forbidden patterns
- Grandidierite tools land in `tools/quarantine/` until promoted
