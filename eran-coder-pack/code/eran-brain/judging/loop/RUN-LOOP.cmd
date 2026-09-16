@echo off
rem ERAN judging loop -- launched hidden via  wscript D:\CLAUDE\run_hidden.vbs D:\CLAUDE\eran-brain\judging\loop\RUN-LOOP.cmd
set PYTHONIOENCODING=utf-8
set LOOP_SITTING=
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" loop.py
