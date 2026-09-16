@echo off
REM ── ער"ן · דשבורד באבל אודיו חי ──────────────────────────────
REM Hear Eran babble, auto-updating in real time. CPU-only (mic keeps the GPU).
cd /d "%~dp0"
echo Starting ERAN live audio-babble dashboard...
start "" http://localhost:8784
python babble_audio_dash.py
pause
