@echo off
rem MAKOM - one read-only page for Iddo on 127.0.0.1:8858. Launched hidden via
rem   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\makom-RUN.cmd"
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" makom.py
