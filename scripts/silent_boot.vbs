' Windowless Matrix boot. wscript //B runs this with zero console.
Option Explicit
Dim sh, root, cmd
Set sh = CreateObject("WScript.Shell")
root = sh.Environment("PROCESS").Item("ETHER_ROOT")
If root = "" Then root = "C:\Users\Otcde\ETHER"
cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & root & "\scripts\matrix_boot.ps1"""
sh.Run cmd, 0, False
