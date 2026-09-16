@echo off
rem Iddo judges CLAUDE's hand-made syllables blind on 127.0.0.1:8857. Launched hidden via
rem   wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\claude-sitting-RUN.cmd"
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\eran-brain\judging
"C:\Program Files\Python312\pythonw.exe" claude_sitting.py
