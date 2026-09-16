@echo off
rem ALMAWARE hidden wrapper - launched by run_hidden.vbs so no console is ever
rem shown. Task Darwish-Daily-Review used to call powershell.exe directly, which
rem flashes a Windows Terminal window at 08:15 (popup hunt 2026-09-15).
rem Edit the .ps1, not this file.
"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\CLAUDE\darwish-ai\daily_review.ps1"
