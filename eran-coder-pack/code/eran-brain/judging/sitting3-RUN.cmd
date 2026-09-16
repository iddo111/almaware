@echo off
rem BLIND SITTING 3 - na and the corpus - on 127.0.0.1:8862 (claude-cli-FABLE-SITTING3 2026-09-03). Launched hidden via
rem   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\sitting3-RUN.cmd"
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" sitting3.py
