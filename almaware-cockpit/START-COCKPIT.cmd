@echo off
REM ALMAWARE COCKPIT - live fleet status
REM Starts the collector daemon (writes status.json every ~5s) and serves the
REM cockpit on http://127.0.0.1:8790/
title ALMAWARE COCKPIT

REM --- collector: only start it if it is not already running -----------------
tasklist /FI "IMAGENAME eq python.exe" /V 2>nul | find /I "collector.py" >nul
if errorlevel 1 (
  echo   starting collector...
  start "ALMA collector" /MIN /D "D:\CLAUDE\almaware-hud" pythonw collector.py
  timeout /t 4 /nobreak >nul
) else (
  echo   collector already running
)

echo   serving cockpit on http://127.0.0.1:8790/
start "" "http://127.0.0.1:8790/"
cd /d "%~dp0"
python -m http.server 8790 --bind 127.0.0.1
