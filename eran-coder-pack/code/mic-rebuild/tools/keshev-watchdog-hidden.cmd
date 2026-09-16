@echo off
REM keshev-watchdog-hidden.cmd - wrapper so the KESHEV-Watchdog scheduled task
REM runs with ZERO visible window (same pattern as quorum: run_hidden.vbs ->
REM this cmd -> powershell -WindowStyle Hidden). Task action is:
REM   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\mic-rebuild\tools\keshev-watchdog-hidden.cmd"
REM 2026-08-18 claude-cli-FABLE, Iddo's goal: a mic that never breaks.
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\CLAUDE\mic-rebuild\tools\keshev-watchdog.ps1" -Once
