# Retired host starters (2026-11-19)

Every file here started, kept alive, or recovered the 1650 writer in an older era
(ETHER.exe window, ether_host one-window loop, ETHER-Daemon/ETHER-Ensure tasks,
ETHER-host.vbs Startup script, ETHER-keepalive XML task, PyInstaller spec).
They raced each other and the GitHub runner tick, and self-heal deleted their tasks.

The ONE start method now: `scripts\install_host.cmd` once, then `scripts\host.cmd start|stop|status`.
It registers a single `ETHER-Host` task -> `scripts/host_supervisor.py` -> `scripts.host_main.tick`.
See docs/HOST_START.md. Do not run anything in this folder.
