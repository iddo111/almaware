@echo off
REM ALMAWARE Hebrew Mic Launcher
REM rez.ai

cd /d "D:\CLAUDE\voice-input"
echo Starting Hebrew Mic...
echo.

set PY=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
if not exist "%PY%" set PY=pythonw

REM Launch supervisor (which launches the mic + UI) — always Python 3.12
start "" "%PY%" supervisor.py
pause
