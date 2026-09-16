@echo off
REM ONE ROOM - the workshop at night.  http://127.0.0.1:8880/
REM BROKEN WINDOWS LAW: if it is not working, fix it immediately.
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Serving the one room on http://127.0.0.1:8880/  (Ctrl+C to stop)
python serve.py
