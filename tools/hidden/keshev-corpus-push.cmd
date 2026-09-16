@echo off
rem ALMAWARE hidden wrapper - launched by run_hidden.vbs so no console is ever
rem shown. Task KESHEV-Corpus-Push used to call powershell.exe directly, and
rem powershell paints a Windows Terminal window before -WindowStyle Hidden applies
rem (caught 2026-09-15 03:00:01 by the popup hunt). Edit the .ps1, not this file.
"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\CLAUDE\mic-rebuild\tools\corpus-push.ps1" -Once
