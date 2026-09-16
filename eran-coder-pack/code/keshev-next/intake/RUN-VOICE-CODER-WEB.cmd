@echo off
rem VOICE CODER WEB -- hold-to-talk on the PHONE, straight into the 480B coder.
rem Standalone process, port 8894 (claimed in RAMCHAT 2026-09-09). Talks only to
rem the ALREADY-RUNNING taste480 page on :8875 (never restarts it) and to the
rem Hebrew STT via phone_mic_web's decoder path. Never opens the PC mic.
rem BELOW_NORMAL per the PC rule -- nothing outranks a live human.
rem
rem Reach it from the phone via: https://<tailnet-host>:8894/
rem (set up once with: tailscale serve --bg --https=8894 http://127.0.0.1:8894)
setlocal
cd /d "%~dp0"
set PY=C:\Program Files\Python312\python.exe
if not exist "%PY%" set PY=python
start "VOICECODER-WEB" /belownormal /min "%PY%" "%~dp0voice_coder_web.py"
endlocal
