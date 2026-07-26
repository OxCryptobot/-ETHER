# Control plane — the real solution

## Problem
Chat agents cannot open a shell on your Windows PC. Ollama/Docker being up does not change that.

## Solution
A **GitHub Actions self-hosted runner** on the Windows host is the remote execution bridge.

```
Grok / CI  --workflow_dispatch-->  GitHub  -->  self-hosted runner (your PC)
                                                    |-
                                                    |- ensure_daemon.ps1
                                                    |- self_test_autonomy.py
                                                    |- health_check / smart cycle
                                                    |- starts ETHER daemon if dead
```

After the runner is installed **once**, no chat paste is required for ensure/E2E:
- schedule every 30 min (`autonomy-host.yml`)
- push to autonomy paths triggers host job
- manual `workflow_dispatch` with action ensure|selftest|health|cycle

## One-time host setup

1. Open https://github.com/OxCryptobot/-ETHER/settings/actions/runners/new
2. Copy the registration token
3. On the Windows box (repo root):

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin; git reset --hard origin/main
powershell -ExecutionPolicy Bypass -File .\scripts\install_self_hosted_runner.ps1 -Token PASTE_TOKEN_HERE
```

4. Confirm runner Idle: https://github.com/OxCryptobot/-ETHER/settings/actions/runners

Also keep OS-level ensure (already in `install_windows_daemon.ps1`) so the daemon survives even if Actions is down.

## Dispatch from API (after runner online)

```
POST /repos/OxCryptobot/-ETHER/actions/workflows/autonomy-host.yml/dispatches
{ "ref": "main", "inputs": { "action": "cycle" } }
```

Actions: `ensure` | `selftest` | `health` | `cycle`
