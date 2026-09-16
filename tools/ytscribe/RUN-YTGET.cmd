@echo off
rem YTGET -- window for yt-dlp + our own transcriber. One click.
setlocal
set PY=C:\Program Files\Python312\python.exe
set ROOT=D:\CLAUDE\tools\ytscribe
set PYTHONIOENCODING=utf-8
cd /d "%ROOT%"
start "" "%PY%" ytgui.py
endlocal
