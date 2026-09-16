@echo off
rem ALMAWARE hidden wrapper - launched by run_hidden.vbs so no console is
rem ever shown, and every child (ssh, scp, git...) inherits this hidden
rem console instead of spawning its own Windows Terminal window.
rem Generated 2026-09-02 for the popup fix. Edit the .ps1, not this file.
"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\CLAUDE\darwish-ai\pull_samples.ps1"
