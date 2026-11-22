#Requires -RunAsAdministrator
<#
ETHER batch 10 (optional, manual, admin): block outbound network for the honest gate's interpreter.

Windows Job Objects cannot block network, so core/agent/gate_jail.py cannot do it by itself.
This script adds one Windows Firewall rule that blocks OUTBOUND traffic for ONE program path.
Nothing in ETHER runs this script; you run it once, by hand, if you want it.

Use a DEDICATED interpreter for the gate, never the one the host itself uses (the host needs
the network for git pull/push and Ollama):

  1. py -3.11 -m venv C:\Users\Otcde\ETHER-gatepy
  2. C:\Users\Otcde\ETHER-gatepy\Scripts\python -m pip install -r <the host's requirements> pytest
  3. .\scripts\gate_firewall.ps1 -Python C:\Users\Otcde\ETHER-gatepy\Scripts\python.exe
  4. setx ETHER_GATE_PYTHON C:\Users\Otcde\ETHER-gatepy\Scripts\python.exe   (then restart the host)

Honest limit: a venv's python.exe is a small launcher that starts the BASE interpreter
(e.g. C:\Python311\python.exe). Windows Firewall matches the process that opens the socket,
i.e. the base interpreter. If that base interpreter is shared with the host, blocking it also
cuts the host off. For a real block, use a separate base Python install (or an embeddable
Python zip) only for the gate and pass ITS python.exe here. Loopback (Ollama on 127.0.0.1)
is not filtered by Windows Firewall.

Remove with:  .\scripts\gate_firewall.ps1 -Remove
#>
param(
    [string]$Python = $env:ETHER_GATE_PYTHON,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$name = "ETHER gate no-network"
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if ($Remove) { Write-Host "Removed rule '$name'."; exit 0 }
if (-not $Python -or -not (Test-Path $Python)) {
    Write-Host "Pass -Python <path to the dedicated gate python.exe> (or set ETHER_GATE_PYTHON)."; exit 1
}
$resolved = (Resolve-Path $Python).Path
New-NetFirewallRule -DisplayName $name -Direction Outbound -Program $resolved -Action Block -Profile Any | Out-Null
Write-Host "Outbound blocked for $resolved"
Write-Host "Check: & '$resolved' -c ""import socket;s=socket.socket();s.settimeout(3);print(s.connect_ex(('1.1.1.1',53)))""  (non-zero = blocked)"
