# Security Policy

## Reporting
If you find a vulnerability in @ETHER, open a private security advisory on the repo or contact the maintainers directly. Do not file a public issue for exploitable bugs.

## Security model (summary)
- LLM output is untrusted until it passes sandbox + audit
- Primary isolation boundary is Docker (`--network none`, `--read-only`, memory/CPU limits)
- AST + regex checks are defense-in-depth only
- Self-generated tools stay in `tools/quarantine/` until explicit `ether promote`
- Orchestrator enforces retry and loop caps to prevent runaway extension

## Non-goals
- Formal verification
- Protection against a compromised Docker host
- Guaranteeing model outputs are always correct
