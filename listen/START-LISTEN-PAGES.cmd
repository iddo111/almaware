@echo off
REM START-LISTEN-PAGES.cmd - brings back the two "listen" toys after a reboot.
REM   :8803  voice ant farm GUI (D:\CLAUDE\voice-ant-farm\gui.py)
REM   :8811  Darwish/ants listen page (D:\CLAUDE\listen, static) on PC + Tailscale
REM Installed as logon task "ALMA-Listen-Pages" 2026-08-18 by claude-cli-FABLE
REM after the 05:07 reboot killed both. Uses python.exe (NOT pythonw) for
REM http.server: with pythonw sys.stderr is None and every request dies in
REM log_message before the response is flushed (measured 05:44 - curl got 000).
set PY=C:\Program Files\Python312\python.exe
cd /d D:\CLAUDE\voice-ant-farm
start "" /min "%PY%" gui.py
cd /d D:\CLAUDE\listen
start "" /min "%PY%" -m http.server 8811 --bind 127.0.0.1
start "" /min "%PY%" -m http.server 8811 --bind <tailnet-ip>
