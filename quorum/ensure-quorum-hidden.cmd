@echo off
REM ensure-quorum-hidden.cmd - wrapper so the QUORUM watchdog task can run via
REM run_hidden.vbs with ZERO visible window. Fix for the popup plague
REM (2026-08-08): the scheduled task ran powershell interactively every 5 min,
REM flashing a console. Task action is now:
REM   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\quorum\ensure-quorum-hidden.cmd"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\CLAUDE\ensure-quorum.ps1"
