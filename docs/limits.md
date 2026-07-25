# Operational limits

- Default sandbox timeout: `ETHER_SANDBOX_TIMEOUT` (60s)
- Max generated code size before sandbox: 50_000 characters
- Orchestrator max retries: 3
- Orchestrator max extension loops: 5
- Concurrent sandboxes: not multiplexed yet — run one heavy `ether run` at a time per machine unless you manage Docker concurrency yourself
