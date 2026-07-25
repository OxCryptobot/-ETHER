# @ETHER Threat Model (short)

## Assets
- User code and local repositories
- Generated tools
- Interaction logs

## Trust boundaries
1. LLM output is untrusted until sandbox + audit pass
2. Docker sandbox is the primary isolation boundary
3. Grandidierite output is untrusted until human promotion

## Main threats & mitigations
| Threat | Mitigation |
|--------|------------|
| Malicious generated code | Docker network-none + read-only + resource limits |
| `eval`/`exec` style payloads | AST + regex filters (defense-in-depth) |
| Infinite extension loops | max_loops in orchestrator |
| Tool supply-chain from self-extension | quarantine + explicit `ether promote` |
| Secret leakage in logs | avoid logging full env; future redaction |

## Non-goals
- Formal verification / mathematical proofs
- Protecting against a compromised Docker daemon
