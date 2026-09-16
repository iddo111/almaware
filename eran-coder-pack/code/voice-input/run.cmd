@echo off
REM ── Hebrew mic, fully automatic: listen -> Hebrew STT (faster-whisper medium, CUDA)
REM    -> auto-type into the focused window -> auto-press Enter. No hotkey to start.
REM    Edit config.json (mode=vad, auto_enter=true) to tune. Ctrl+C to stop.
REM    rez.ai
title Claude - Hebrew Mic Auto (PC)
cd /d "%~dp0"
echo Starting fully-auto Hebrew mic (VAD + auto-type + auto-enter)...
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python
"%PY%" voice_input.py --vad --enter
