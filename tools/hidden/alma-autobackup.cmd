@echo off
rem ALMAWARE hidden wrapper - launched by run_hidden.vbs so no console is
rem ever shown, and every child (ssh, scp, git...) inherits this hidden
rem console instead of spawning its own Windows Terminal window.
rem Generated 2026-09-02 for the popup fix. Edit the .ps1, not this file.
"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\CLAUDE\alma-backup\alma_backup.ps1"
