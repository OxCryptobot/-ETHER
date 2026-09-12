# ETHER product (one path)

Engine: `scripts/ether_app.py` or `ETHER.exe` after a green `build-exe` run.
Live view: Grok Control Matrix only (`?view=bus`). Dual chat is locked.
Root on this machine: `C:\\Users\\Otcde\\ETHER` (`ETHER_ROOT`).

Do not run: old `.cmd`, `.bat`, `.vbs`, `attach_1650.ps1`, desktop harness, `:8787` cockpit.
`:8787` is headless health/API. The HTML Control Matrix there is retired (HTTP 410).
FAST proof: GitHub `matrix-worker`. Not the GPU.
LIVE: Ollama on the 1650 inside the engine process.

Attach is a report (`artifacts/host_attach.json`). If the engine ran, origin gets `1650 app attach`.
If it did not, the engine did not reach this folder.

Build EXE: Actions workflow `build-exe` → artifact `ETHER-exe`.
