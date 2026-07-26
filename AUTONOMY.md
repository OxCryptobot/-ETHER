# @ETHER Autonomy Contract

## Truth

**Code loop is closed.** Once the daemon process is alive, it self-heals, requeues failures, recovers metrics, drains batch, and restarts dead worker threads without a human in the chat loop.

**Not magic:** a host OS process must exist. Scheduled Task / start_daemon registers that once. After that, autonomy owns the loop.

## Closed loops (implemented)

1. Curriculum samples failure-driven + tier tasks (assert-nudged)
2. Pipeline records verification_score → experience → promote only on verified wins
3. Failures auto-enqueue to batch
4. Empty queue auto-seeds smoke
5. Unhealthy → recovery_cycle (holdout expand → bench → quiz → scoreboard → guardian baseline)
6. Guardian can unfreeze when metrics recover
7. Daemon boot runs `scripts/self_test_autonomy.py`
8. Watchdog restarts dead flywheel/batch/dashboard threads
9. Batch queue exclusive lock for concurrent safety

## Proof artifacts (written by the system)

- `memory/daemon/heartbeat.txt`
- `memory/daemon/healthy.json`
- `memory/daemon/autonomy.jsonl`
- `memory/flywheel/latest.json` + history
- `memory/batch_queue.json`
- `SCOREBOARD.md`

## Offline self-test

```
python scripts/self_test_autonomy.py
```

No Ollama required. Exit 0 = autonomy substrate intact.
