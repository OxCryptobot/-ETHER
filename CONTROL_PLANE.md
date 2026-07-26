# Control plane — the real solution

## Problem
Chat agents cannot open a shell on your Windows PC. Ollama/Docker being up does not change that.

## Solution
A **GitHub Actions self-hosted runner** on the Windows host is the remote execution bridge.

Supports **Windows x64 and Windows ARM64** (Snapdragon / WoA). Install script auto-selects `win-x64` or `win-arm64` runner asset.

```
Grok / CI  --workflow_dispatch-->  GitHub  -->  self-hosted runner (your PC)
                                                    |-
                                                    |- ensure_daemon.ps1
                                                    |- self_test_autonomy.py
                                                    |- health_check / smart cycle
                                                    |- starts ETHER daemon if dead
```

## One-time host setup (ARM64 or x64)

1. https://github.com/OxCryptobot/-ETHER/settings/actions/runners/new → copy token
2. Repo root:

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin; git reset --hard origin/main
powershell -ExecutionPolicy Bypass -File .\scripts\install_self_hosted_runner.ps1 -Token PASTE_TOKEN_HERE
```

3. Confirm Idle: https://github.com/OxCryptobot/-ETHER/settings/actions/runners  
   Labels should include `self-hosted`, `Windows`, `ETHER`, and `ARM64` or `X64`.

Also register OS ensure (daemon survives if Actions is down):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_daemon.ps1
```

## Notes for ARM64 Windows
- Use ARM64 native Python 3.11+ in PATH (or x64 Python under emulation — native preferred).
- Ollama ARM64 build if available for your device; Docker Desktop supports Windows on ARM with limitations — ETHER falls back to local subprocess sandbox when Docker is unavailable.
- Runner asset is `actions-runner-win-arm64-*.zip`, not x64.

## Dispatch after runner online

```
POST /repos/OxCryptobot/-ETHER/actions/workflows/autonomy-host.yml/dispatches
{ "ref": "main", "inputs": { "action": "cycle" } }
```

Actions: `ensure` | `selftest` | `health` | `cycle`
