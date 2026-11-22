# @ETHER — one process only

> **2026-11-19:** the only way to start the 1650 writer is `scripts\install_host.cmd` (once) and `scripts\host.cmd start|stop|status`. See [docs/HOST_START.md](docs/HOST_START.md). Older launchers are in `scripts/_graveyard/host_legacy/`.


You need **1 window max**, not 4.

## Recommended (always works)

```powershell
cd C:\Users\Otcde\ETHER
scripts\host.cmd start
```

- Pulls latest from git
- Stops old processes
- Runs **one** Python: flywheel + batch + dashboard
- Leave that window open (or minimize)

Status: the Grok Control Matrix (read-only) reads `artifacts/unison.json`, `supervisor.json` and `learning_summary.json` from origin; locally `scripts/ether_app.py` serves a read-only watch page on http://127.0.0.1:7843/. The old :8787 dashboard is retired (writes refused, batch 9).

## Stop

```powershell
scripts\host.cmd stop
```

## Optional background (0 windows)

```powershell
scripts\host.cmd start
```

If background fails, use the default foreground command above.
