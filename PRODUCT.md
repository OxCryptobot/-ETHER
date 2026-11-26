# ETHER product

One process on the 1650. `scripts/host_main.py` starts `core/kernel/agent.py`.
The cycle is perceive, decide, edit, verify, remember.
Matrix is the view. It does not start, stop, or edit.
There is no `ETHER.exe`. Do not build another one.

`honest` is true only after a tool edit and a passing test.
Git is the publish step, not the brain. A job file is not the brain.

Swarm (opt-in; owner decision 2026-11-22, audit D1): a swarm here is single-writer and runs one 4B
model call at a time. Inside the one host process, deterministic CPU agents (scouts, critics: gem, AST,
lint, LSP) and, when `ETHER_SWARM=1`, a few serial 4B samples propose; `scripts/host_main.py` stays the
only writer and only the honest gate keeps an edit. Off by default (`ETHER_SWARM=0`; `record` = shadow).

Not this product: a trading bot, a second writer, a GPU fan-out swarm (two models or two writers at once), port 8787.
Next gate: the 1650 process publishes `app_alive`, then the same edit passes twice.
