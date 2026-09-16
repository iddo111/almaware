@echo off
rem PHONE MIC WEB -- the page Iddo opens on his PHONE.
rem Standalone process, port 8893 (claimed in RAMCHAT). Talks only to the
rem ALREADY-RUNNING intake sidecar on :8892 (never restarts it) and to
rem eran1's STT over the LAN. Never opens the PC mic, never touches KESHEV.
rem BELOW_NORMAL per the PC rule -- nothing outranks a live human.
rem
rem Reach it from the phone via: https://<tailnet-host>:8893/
rem (set up once with: tailscale serve --bg --https=8893 http://127.0.0.1:8893)
setlocal
cd /d "%~dp0"
set PY=C:\Program Files\Python312\python.exe
if not exist "%PY%" set PY=python
start "PHONEMIC-WEB" /belownormal /min "%PY%" "%~dp0phone_mic_web.py"
endlocal
