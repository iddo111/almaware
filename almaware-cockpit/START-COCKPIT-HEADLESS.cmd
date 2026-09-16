@echo off
REM ALMAWARE COCKPIT (HEADLESS) - infra-rebuild Stage 1.4, 2026-08-12
REM Same as START-COCKPIT.cmd MINUS the browser auto-open (unwanted at logon).
REM Starts the collector daemon (writes status.json every ~5s) and serves the
REM cockpit on http://127.0.0.1:8790/ - open the URL yourself when needed.
REM Used by scheduled task ALMA-Orphan-Cockpit (logon + PT7M delay).
title ALMAWARE COCKPIT HEADLESS

REM --- collector: only start it if it is not already running -----------------
REM (real command-line check; the old tasklist/title grep missed pythonw)
powershell -NoProfile -Command "exit @(Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'collector\.py' }).Count"
if %errorlevel%==0 (
  echo   starting collector...
  start "ALMA collector" /MIN /D "D:\CLAUDE\almaware-hud" "C:\Users\<user>\AppData\Local\Programs\Python\Python313\pythonw.exe" collector.py
  timeout /t 4 /nobreak >nul
) else (
  echo   collector already running
)

echo   serving cockpit on http://127.0.0.1:8790/  (no browser auto-open)
cd /d "%~dp0"
"C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe" -m http.server 8790 --bind 127.0.0.1
