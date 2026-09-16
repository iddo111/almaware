@echo off
rem ERAN's school — blind A/B sitting on 127.0.0.1:8855. Launched hidden via
rem   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\school-RUN.cmd"
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" school.py
