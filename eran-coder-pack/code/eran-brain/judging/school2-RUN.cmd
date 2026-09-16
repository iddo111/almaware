@echo off
rem ERAN school v2 - blind A/B sitting on 127.0.0.1:8856 (claude-cli-MOREH 2026-09-03). Launched hidden via
rem   wscript.exe "D:\CLAUDEun_hidden.vbs" "D:\CLAUDE\eran-brain\judging\school2-RUN.cmd"
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" school2.py
