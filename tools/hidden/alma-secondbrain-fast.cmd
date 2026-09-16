@echo off
rem ALMAWARE hidden wrapper - launched by run_hidden.vbs so no console is
rem ever shown, and every child (ssh, scp, python...) inherits this hidden
rem console instead of spawning its own Windows Terminal window.
rem Generated 2026-09-05 for the SECOND BRAIN fast tier. Edit the .ps1, not this file.
"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\CLAUDE\alma-backup\second_brain_fast.ps1"
