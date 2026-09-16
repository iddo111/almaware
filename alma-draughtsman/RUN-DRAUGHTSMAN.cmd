@echo off
rem ALMA DRAUGHTSMAN -- the studio window. One click.
rem The window NEVER plays audio (Sacred Audio Law); it draws and writes a file.
setlocal
set PY=C:\Program Files\Python312\python.exe
set ROOT=D:\CLAUDE\alma-draughtsman
set PYTHONIOENCODING=utf-8
cd /d "%ROOT%"
start "" "%PY%" gui.py
endlocal
