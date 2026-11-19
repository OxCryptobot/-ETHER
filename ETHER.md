# ETHER

Local-first coding agent. Face is the Control Matrix. Hands are `scripts/host_main.py` on the 1650, kept alive by the one `ETHER-Host` task (docs/HOST_START.md).

## Doctrine
- Matrix is read-only. It does not start Ollama, enqueue jobs, or write attach.
- host_main (under ETHER-Host) is the only writer (git, Ollama, FIFO, scoreboard, attach). There is no ETHER.exe.
- Tool-first. Generate-fallback is never PASS.
- Read the failing test first. Surgical patch. run_tests. Abort on no-progress.
- Labradorite critique before a second hypothesis.
- Training wheels ON until honest hard LIVE is repeatable.
- No second installer. Disk git pull updates the writer.
- No operator PowerShell.

## Tools
Emit one JSON tool call per step. Prefer apply_patch over write_file.
