@echo off
rem GALERIA - every model, its real outputs, to see and hear. 127.0.0.1:8861 (claude-cli-FABLE 2026-09-03).
rem   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\galeria-RUN.cmd"
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" galeria.py
